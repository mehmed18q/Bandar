"""Supervise one ``kubectl port-forward`` process as an explicit state machine.

    stopped ──start──▶ starting ──"Forwarding from"──▶ healthy
       ▲                  │  ▲                            │
       │             failure │ backoff timer         failure / broken tunnel
       │                  ▼  │                            │
       └──stop──── retrying ◀──────────(retryable)────────┘
                       │
                (not retryable or attempts exhausted)
                       ▼
                     error ──retry──▶ starting

All process I/O is signal driven through QProcess, so nothing here blocks the
UI thread. Each launched process carries a generation number; output from a
process that has been replaced is ignored.
"""

from __future__ import annotations

import shutil
import sys
import time
from collections import deque
from enum import StrEnum
from functools import partial

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QAbstractSocket, QTcpSocket

from bandar.core import ports
from bandar.core.commands import build_args, display_command
from bandar.core.diagnostics import Problem, classify, clean_line, runtime_event
from bandar.runtime.retry import RetryPolicy

COMMAND_FIELDS = (
    "context",
    "namespace",
    "kind",
    "target",
    "localPort",
    "remotePort",
    "address",
    "extraArgs",
)
STABLE_AFTER = 60.0  # seconds a tunnel must stay healthy before backoff resets
TERMINATE_GRACE_MS = 3000
LOG_LIMIT = 500


class State(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    HEALTHY = "healthy"
    RETRYING = "retrying"
    ERROR = "error"
    STOPPING = "stopping"


ACTIVE = {State.STARTING, State.HEALTHY, State.RETRYING}
PORT_PROBLEMS = {
    "busy": "port_in_use",
    "denied": "port_denied",
    "unavailable": "address_unavailable",
}


# On Linux every kubectl is started through setpriv with a parent-death signal: if
# Bandar crashes or is killed, the kernel stops its port-forwards too. A normal
# quit stops them explicitly (ForwardManager.shutdown).
DEATH_WRAPPER = shutil.which("setpriv") if sys.platform.startswith("linux") else None


def command_line(kubectl: str, args: list) -> tuple:
    """``(program, arguments)`` to launch, or ``(None, reason)`` when kubectl is missing."""
    resolved = shutil.which(kubectl)
    if not resolved:
        return None, f"{kubectl}: not found (install kubectl or set its path in Settings)"
    if DEATH_WRAPPER:
        return DEATH_WRAPPER, ["--pdeathsig", "TERM", "--", resolved, *args]
    return resolved, list(args)


def _ms(seconds):
    return int(seconds * 1000) if seconds else None


def _probe_host(address: str) -> str:
    first = address.split(",")[0].strip()
    return {"localhost": "127.0.0.1", "0.0.0.0": "127.0.0.1", "::": "::1"}.get(first, first)


class Forward(QObject):
    """One configured service and the process that serves it."""

    changed = Signal(str)
    logged = Signal(str, object)
    failed = Signal(str, object)
    recovered = Signal(str, object)

    def __init__(self, service: dict, settings, tasks, parent=None):
        super().__init__(parent)
        self.service = dict(service)
        self._settings = settings
        self._tasks = tasks
        self.state = State.STOPPED
        self.desired = False
        self.attempt = 0
        self.restarts = 0
        self.connections = 0
        self.started_at = None
        self.healthy_since = None
        self.retry_at = None
        self.last_activity = None
        self.error = None
        self.last_error = None
        self.warning = None
        self.context = ""
        self.logs = deque(maxlen=LOG_LIMIT)
        self._process = None
        self._generation = 0
        self._relaunch = False
        self._exiting = False
        self._fatal = None
        self._stderr = deque(maxlen=30)
        self._buffers = {}
        self._probe_mark = 0.0
        self._retry_timer = self._timer(self._retry_due)
        self._ready_timer = self._timer(self._ready_timeout)
        self._kill_timer = self._timer(self._kill_now)
        self._probe_timer = QTimer(self)
        self._probe_timer.timeout.connect(self._probe)

    def _timer(self, slot):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(slot)
        return timer

    @property
    def id(self) -> str:
        return self.service["id"]

    @property
    def pid(self):
        return self._process.processId() if self._process else None

    # ------------------------------------------------------------ commands

    def start(self, resolved_context: str = ""):
        """Begin forwarding. Calling it while already active does nothing."""
        if self.desired and self.state in ACTIVE:
            return
        if self.state == State.ERROR and self.desired:
            self.restart(resolved_context)
            return
        self.desired = True
        self.started_at = time.time()
        self.attempt = self.restarts = self.connections = 0
        self.error = self.warning = self.last_error = None
        self.context = self.service["context"] or resolved_context
        self._launch()

    def stop(self):
        self.desired = False
        self._relaunch = False
        for timer in (self._retry_timer, self._ready_timer, self._probe_timer):
            timer.stop()
        self.retry_at = self.healthy_since = self.started_at = None
        self.error = self.warning = None
        self.attempt = 0
        if self._process:
            self._log("info", "Stopping")
            self._set_state(State.STOPPING)
            self._terminate()
        else:
            self._set_state(State.STOPPED)

    def restart(self, resolved_context: str = "", count: bool = True):
        """Reconnect now, resetting backoff. Used for manual retries and edits."""
        self.desired = True
        self.attempt = 0
        self.error = self.warning = None
        self.retry_at = None
        self._retry_timer.stop()
        self.started_at = self.started_at or time.time()
        self.context = self.service["context"] or resolved_context or self.context
        if count and self.state != State.STOPPED:
            self.restarts += 1
        if self._process:
            self._relaunch = True
            self._set_state(State.STARTING)
            self._terminate()
        else:
            self._launch()

    def reconfigure(self, service: dict, resolved_context: str = ""):
        """Apply an edited service; a running tunnel is rebuilt only if its command changed."""
        command_changed = any(self.service.get(key) != service.get(key) for key in COMMAND_FIELDS)
        self.service = dict(service)
        if command_changed and self.desired:
            self._log("info", "Configuration changed, reconnecting")
            self.restart(resolved_context, count=False)
        else:
            self.changed.emit(self.id)

    def refuse(self, problem: Problem):
        """Record a problem detected before launch (e.g. a port clash between services)."""
        self.desired = True
        self.started_at = self.started_at or time.time()
        self._fail(problem)

    def terminate_for_exit(self):
        """Ask the process to stop without changing remembered state (application exit)."""
        self._exiting = True
        for timer in (self._retry_timer, self._ready_timer, self._probe_timer, self._kill_timer):
            timer.stop()
        if self._process:
            self._process.terminate()
        return self._process

    def clear_logs(self):
        self.logs.clear()

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "state": str(self.state),
            "desired": self.desired,
            "attempt": self.attempt,
            "restarts": self.restarts,
            "connections": self.connections,
            "startedAt": _ms(self.started_at),
            "healthySince": _ms(self.healthy_since),
            "retryAt": _ms(self.retry_at),
            "lastActivity": _ms(self.last_activity),
            "error": self.error,
            "lastError": self.last_error,
            "warning": self.warning,
            "context": self.context,
            "pid": self.pid,
        }

    # ------------------------------------------------------------ process lifecycle

    def _launch(self):
        self._retry_timer.stop()
        self.retry_at = None
        if not self.desired:
            return
        if self._process:
            self._relaunch = True
            return
        settings = self._settings()
        port, address = self.service["localPort"], self.service["address"]
        port_state = ports.status(port, address)
        if port_state != "free":
            problem = Problem(PORT_PROBLEMS[port_state], False, f"{address}:{port}")
            self._log("error", f"Cannot listen on {address}:{port} ({port_state})")
            self._fail(problem)
            if port_state == "busy":
                self._lookup_owner(port)
            return
        program, arguments = command_line(settings["kubectl"], build_args(self.service, settings))
        if program is None:
            self._log("error", arguments)
            self._fail(Problem("kubectl_missing", False, arguments))
            return
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(arguments)
        self._generation += 1
        generation = self._generation
        process.readyReadStandardOutput.connect(partial(self._read, process, generation, "out"))
        process.readyReadStandardError.connect(partial(self._read, process, generation, "err"))
        process.errorOccurred.connect(partial(self._process_error, process, generation))
        process.finished.connect(partial(self._process_finished, process, generation))
        self._process = process
        self._buffers = {"out": b"", "err": b""}
        self._stderr.clear()
        self._fatal = None
        self.healthy_since = None
        self._set_state(State.STARTING)
        self._log("cmd", display_command(self.service, settings))
        process.start()
        self._ready_timer.start(settings["startTimeout"] * 1000)

    def _read(self, process, generation, channel):
        if generation != self._generation:
            return
        reader = process.readAllStandardOutput if channel == "out" else process.readAllStandardError
        try:
            chunk = bytes(reader().data())
        except RuntimeError:  # the QProcess was destroyed together with its owner
            return
        data = self._buffers.get(channel, b"") + chunk
        *lines, rest = data.split(b"\n")
        self._buffers[channel] = rest[-8192:]
        for raw in lines:
            line = raw.decode(errors="replace").rstrip("\r")
            if line.strip():
                (self._on_stdout if channel == "out" else self._on_stderr)(line)

    def _flush(self, process, generation):
        self._read(process, generation, "out")
        self._read(process, generation, "err")
        for channel, rest in list(self._buffers.items()):
            if rest.strip():
                line = rest.decode(errors="replace")
                (self._on_stdout if channel == "out" else self._on_stderr)(line)
        self._buffers = {}

    def _on_stdout(self, line):
        if line.startswith("Handling connection for"):
            now = time.time()
            if now - self._probe_mark > 2:
                self.connections += 1
                self.last_activity = now
                self.changed.emit(self.id)
            return
        self._log("info", line)
        if line.startswith("Forwarding from") and self.state == State.STARTING:
            self._ready_timer.stop()
            self.healthy_since = time.time()
            recovering = self.error is not None
            if recovering:
                self.last_error = self.error
            self.error = None
            self._set_state(State.HEALTHY)
            if recovering:
                self.recovered.emit(self.id, self.snapshot())
            interval = self._settings()["healthCheckInterval"]
            if interval:
                self._probe_timer.start(interval * 1000)

    def _on_stderr(self, line):
        self._stderr.append(line)
        self._log("error", clean_line(line) or line)
        if self.state != State.HEALTHY:
            return
        event = runtime_event(line)
        if event is None:
            return
        kind, problem = event
        if kind == "warning":
            self.warning = problem.as_dict(at=_ms(time.time()))
            self.changed.emit(self.id)
        elif self._fatal is None:
            self._fatal = problem
            self._log("warn", "The tunnel is broken, reconnecting")
            self._terminate()

    def _process_error(self, process, generation, error):
        if error != QProcess.ProcessError.FailedToStart or generation != self._generation:
            return
        self._discard(process)
        self._ready_timer.stop()
        detail = f"{process.program()}: {process.errorString()}"
        self._log("error", detail)
        if self._relaunch or not self.desired:
            self._relaunch = False
            self._set_state(State.STOPPED)
            return
        self._fail(Problem("kubectl_missing", False, detail))

    def _process_finished(self, process, generation, exit_code, _status):
        if generation != self._generation:
            return
        self._flush(process, generation)
        self._discard(process)
        for timer in (self._ready_timer, self._probe_timer, self._kill_timer):
            timer.stop()
        if self._exiting:  # application exit: keep ``desired`` so the session resumes
            self.state = State.STOPPED
            return
        if self._relaunch:
            self._relaunch = False
            if self.desired:
                self._launch()
                return
        if not self.desired:
            self._log("info", "Stopped")
            self._set_state(State.STOPPED)
            return
        if self._fatal:
            problem = self._fatal
        elif self._stderr:
            problem = classify("\n".join(self._stderr))
        else:
            problem = Problem("exited", True, f"kubectl exited with code {exit_code}")
        self._fail(problem)

    def _discard(self, process):
        if self._process is process:
            self._process = None
        process.deleteLater()

    def _terminate(self):
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.terminate()
            self._kill_timer.start(TERMINATE_GRACE_MS)

    def _kill_now(self):
        if self._process:
            self._log("warn", "kubectl did not exit, killing it")
            self._process.kill()

    # ------------------------------------------------------------ failure handling

    def _fail(self, problem: Problem):
        now = time.time()
        if self.healthy_since and now - self.healthy_since >= STABLE_AFTER:
            self.attempt = 0
        self.healthy_since = None
        self.error = problem.as_dict(at=_ms(now))
        policy = RetryPolicy.from_settings(self._settings())
        if self.desired and policy.allows(self.attempt + 1, problem):
            self.attempt += 1
            delay = policy.delay(self.attempt)
            self.retry_at = now + delay
            self._retry_timer.start(int(delay * 1000))
            self._log("warn", f"Retrying in {delay:.1f}s (attempt {self.attempt})")
            self._set_state(State.RETRYING)
        else:
            self.retry_at = None
            self._set_state(State.ERROR)
        self.failed.emit(self.id, self.snapshot())

    def _retry_due(self):
        if self.desired and self.state == State.RETRYING:
            self.restarts += 1
            self._launch()

    def _ready_timeout(self):
        if self.state == State.STARTING and self._process:
            seconds = self._settings()["startTimeout"]
            self._fatal = Problem("start_timeout", True, f"No response from kubectl in {seconds}s")
            self._terminate()

    def _lookup_owner(self, port):
        generation = self._generation

        def attach(owner):
            stale = generation != self._generation or not self.error
            if stale or isinstance(owner, Exception) or self.error.get("code") != "port_in_use":
                return
            self.error = {**self.error, "owner": owner}
            self.changed.emit(self.id)

        self._tasks.run(ports.owner, port, callback=attach)

    # ------------------------------------------------------------ active health check

    def _probe(self):
        if self.state != State.HEALTHY:
            self._probe_timer.stop()
            return
        generation = self._generation
        socket = QTcpSocket(self)
        self._probe_mark = time.time()

        def refused(error):
            refused_now = error == QAbstractSocket.SocketError.ConnectionRefusedError
            if refused_now and generation == self._generation and self.state == State.HEALTHY:
                self._fatal = Problem("listener_lost", True, "The local listener disappeared")
                self._terminate()
            socket.deleteLater()

        socket.connected.connect(lambda: (socket.abort(), socket.deleteLater()))
        socket.errorOccurred.connect(refused)
        socket.connectToHost(_probe_host(self.service["address"]), self.service["localPort"])
        QTimer.singleShot(5000, socket, socket.abort)

    # ------------------------------------------------------------ bookkeeping

    def _set_state(self, state: State):
        self.state = state
        self.changed.emit(self.id)

    def _log(self, level, text):
        entry = {"t": _ms(time.time()), "level": level, "text": text[:2000]}
        self.logs.append(entry)
        self.logged.emit(self.id, entry)
