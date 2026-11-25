"""Notice any loss of connectivity to a cluster and rebuild the affected tunnels.

``kubectl port-forward`` keeps running with a dead connection to the API server
and prints nothing until a client connects, so a dropped VPN looks healthy. The
watchdog asks each cluster in use for ``/version`` (cheap, needs no special
rights, never touches the forwarded databases) on an interval, and right away
when the machine's network interfaces change (a VPN coming up or down):

* unreachable  → the tunnels of that context are rebuilt; the normal failure path
  retries with backoff and notifies the user;
* reachable again → tunnels waiting out a backoff retry immediately.

A slow answer must repeat before tunnels are dropped; errors that prove the
cluster is gone (no route, name resolution) act at once.

A network that drops and returns between checks (sleep, Wi-Fi or VPN reconnect)
leaves kubectl holding dead connections while the cluster answers again. So after
any network change or wake-up, tunnels established before it are rebuilt once
their cluster answers. Container and VM interfaces are ignored.
"""

from __future__ import annotations

import logging
import re
import time
from functools import partial

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QNetworkInterface

from bandar.core.diagnostics import Problem, classify, definitely_unreachable
from bandar.runtime.forward import command_line

log = logging.getLogger(__name__)
PROBE_DEADLINE_MS = 9000
SLOW_FAILURES_BEFORE_ACTION = 2
NETWORK_POLL_MS = 3000
NETWORK_SETTLE_MS = 1500
UNREACHABLE = {"api_unreachable", "timeout", "connection_lost"}
SUSPEND_GAP_SECONDS = 25  # a timer late by this much means the machine was asleep
# Container, VM and loopback interfaces come and go without affecting the route to a cluster.
VIRTUAL = re.compile(
    r"^(lo|veth|docker|br-|virbr|vnet|vmnet|vboxnet|cni|flannel|cali|kube|lxc|lxd|tap)"
)


def network_signature() -> tuple:
    """Physical and VPN interfaces that are up, with their IPv4 addresses.

    IPv6 is left out on purpose: temporary addresses rotate on their own.
    """
    signature = []
    for interface in QNetworkInterface.allInterfaces():
        if VIRTUAL.match(interface.name()):
            continue
        if not (interface.flags() & QNetworkInterface.InterfaceFlag.IsUp):
            continue
        addresses = sorted(
            entry.ip().toString()
            for entry in interface.addressEntries()
            if ":" not in entry.ip().toString()
        )
        signature.append((interface.name(), tuple(addresses)))
    return tuple(sorted(signature))


class NetworkMonitor(QObject):
    """Polls the interface list (in-process, cheap); reports changes and wake-ups."""

    changed = Signal(str)  # "interfaces" or "resumed"

    def __init__(
        self, parent=None, interval_ms=NETWORK_POLL_MS, read=network_signature, clock=time.time
    ):
        super().__init__(parent)
        self._read = read
        self._clock = clock
        self._last = read()
        self._tick = clock()
        self._interval = interval_ms / 1000
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(interval_ms)

    def _poll(self):
        now = self._clock()
        slept = now - self._tick > self._interval + SUSPEND_GAP_SECONDS
        self._tick = now
        current = self._read()
        if slept:
            log.info("Woke up from sleep")
            self._last = current
            self.changed.emit("resumed")
        elif current != self._last:
            self._last = current
            log.info("Network interfaces changed")
            self.changed.emit("interfaces")

    def stop(self):
        self._timer.stop()


class ClusterWatchdog(QObject):
    checked = Signal(str, bool, object)  # context, reachable, problem dict or None

    def __init__(self, manager, settings, parent=None, monitor=True):
        super().__init__(parent)
        self._manager = manager
        self._settings = settings
        self._probes = {}
        self._slow = {}
        self._changed_at = None  # when the network last changed; tunnels older than it are suspect
        self._suspect = set()  # contexts whose tunnels still need a rebuild after that change
        self.unreachable = set()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_now)
        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(NETWORK_SETTLE_MS)
        self._settle.timeout.connect(self.check_now)
        self._network = NetworkMonitor(self) if monitor else None
        if self._network:
            self._network.changed.connect(self.network_changed)

    # ------------------------------------------------------------ control

    def start(self):
        self.apply_settings()

    def apply_settings(self):
        seconds = self._settings()["clusterCheckInterval"]
        if seconds:
            self._timer.start(seconds * 1000)
        else:
            self._timer.stop()

    def stop(self):
        self._timer.stop()
        self._settle.stop()
        if self._network:
            self._network.stop()
        for process in list(self._probes.values()):
            process.kill()
            process.waitForFinished(300)
        self._probes.clear()

    def network_changed(self, reason="interfaces"):
        """Connections opened before now may be dead: re-check, then rebuild them."""
        self._changed_at = time.time()
        self._suspect = set(self._manager.contexts_in_use())
        log.info("Network change (%s): re-checking %d context(s)", reason, len(self._suspect))
        self._settle.start()

    def check_now(self):
        if not self._settings()["clusterCheckInterval"]:
            return
        for context in self._manager.contexts_in_use():
            self._probe(context)

    # ------------------------------------------------------------ probes

    def _probe(self, context: str):
        if context in self._probes:
            return
        settings = self._settings()
        args = ["--kubeconfig", settings["kubeconfig"]] if settings.get("kubeconfig") else []
        args += ["--context", context] if context else []
        args += ["get", "--raw", "/version", "--request-timeout=6s"]
        program, arguments = command_line(settings["kubectl"], args)
        if program is None:
            return
        process = QProcess(self)
        deadline = QTimer(process)
        deadline.setSingleShot(True)
        deadline.timeout.connect(process.kill)
        process.finished.connect(partial(self._finished, context, process, deadline))
        process.errorOccurred.connect(
            lambda error: error == QProcess.ProcessError.FailedToStart and self._forget(context)
        )
        self._probes[context] = process
        process.start(program, arguments)
        deadline.start(PROBE_DEADLINE_MS)

    def _forget(self, context):
        process = self._probes.pop(context, None)
        if process:
            process.deleteLater()

    def _finished(self, context, process, deadline, code, _status):
        timed_out = not deadline.isActive()
        deadline.stop()
        text = bytes(process.readAllStandardError().data()).decode(errors="replace")
        self._forget(context)
        if code == 0 and not timed_out:
            self._reachable(context)
            return
        problem = (
            Problem("api_unreachable", True, "The cluster did not answer in time")
            if timed_out
            else classify(text)
        )
        if problem.code not in UNREACHABLE:
            # e.g. expired credentials: existing tunnels may still work; leave them alone.
            self.checked.emit(context, True, problem.as_dict())
            return
        self._slow[context] = self._slow.get(context, 0) + 1
        if definitely_unreachable(text) or self._slow[context] >= SLOW_FAILURES_BEFORE_ACTION:
            if context not in self.unreachable:
                log.warning("Cluster %s is unreachable: %s", context or "(current)", problem.detail)
            self.unreachable.add(context)
            self._manager.lose(context, Problem("api_unreachable", True, problem.detail))
        self.checked.emit(context, False, problem.as_dict())

    def _reachable(self, context):
        self._slow.pop(context, None)
        if context in self.unreachable:
            self.unreachable.discard(context)
            log.info("Cluster %s is reachable again", context or "(current)")
        if context in self._suspect:
            self._suspect.discard(context)
            self._manager.refresh(context, self._changed_at)
        self._manager.hurry(context)
        self.checked.emit(context, True, None)
