"""A facade over every Forward: lifecycle commands, conflict checks and snapshots."""

from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QObject, QTimer, Signal

from bandar.core.config import addresses_overlap
from bandar.core.diagnostics import Problem
from bandar.runtime.forward import ACTIVE, Forward, State

PUSH_DELAY_MS = 40


class ForwardManager(QObject):
    """Owns one Forward per configured service and keeps them in sync with the config.

    ``changed`` is coalesced: a burst of state changes (a group starting) reaches
    the interface as a single update.
    """

    changed = Signal()
    logged = Signal(str, object)
    failed = Signal(str, object)
    recovered = Signal(str, object)

    def __init__(self, settings, tasks, context_resolver=lambda: "", parent=None):
        super().__init__(parent)
        self._settings = settings
        self._tasks = tasks
        self._current_context = context_resolver
        self._forwards: dict[str, Forward] = {}
        self._push = QTimer(self)
        self._push.setSingleShot(True)
        self._push.setInterval(PUSH_DELAY_MS)
        self._push.timeout.connect(self.changed)

    # ------------------------------------------------------------ configuration

    def sync(self, services: list):
        """Create, update or retire forwards so they match ``services``."""
        wanted = {service["id"]: service for service in services}
        for sid in [sid for sid in self._forwards if sid not in wanted]:
            forward = self._forwards.pop(sid)
            forward.stop()
            forward.changed.disconnect()
            QTimer.singleShot(10_000, forward.deleteLater)  # let the process exit first
        for sid, service in wanted.items():
            forward = self._forwards.get(sid)
            if forward is None:
                self._forwards[sid] = self._create(service)
            elif forward.service != service:
                forward.reconfigure(service, self._current_context())
        self._push.start()

    def _create(self, service):
        forward = Forward(service, self._settings, self._tasks, self)
        forward.changed.connect(lambda _id: self._push.start())
        forward.logged.connect(self.logged)
        forward.failed.connect(self.failed)
        forward.recovered.connect(self.recovered)
        return forward

    # ------------------------------------------------------------ commands

    def start(self, ids):
        for sid in self._known(ids):
            forward = self._forwards[sid]
            rival = self._port_rival(forward)
            if rival:
                forward.refuse(Problem("port_conflict", False, rival.service["name"]))
                continue
            forward.start(self._current_context())

    def stop(self, ids):
        for sid in self._known(ids):
            self._forwards[sid].stop()

    def restart(self, ids):
        for sid in self._known(ids):
            forward = self._forwards[sid]
            rival = self._port_rival(forward)
            if rival:
                forward.refuse(Problem("port_conflict", False, rival.service["name"]))
                continue
            forward.restart(self._current_context())

    def _known(self, ids):
        return [sid for sid in dict.fromkeys(ids) if sid in self._forwards]

    def _port_rival(self, forward):
        """Another active forward that already serves the same local address and port."""
        for other in self._forwards.values():
            if other is forward or not (other.desired and other.state in ACTIVE | {State.STOPPING}):
                continue
            same_port = other.service["localPort"] == forward.service["localPort"]
            if same_port and addresses_overlap(
                other.service["address"], forward.service["address"]
            ):
                return other
        return None

    def lose(self, context: str, problem: Problem):
        """Rebuild every tunnel that goes through ``context`` (its cluster is unreachable)."""
        for forward in self._forwards.values():
            if forward.context_key == context:
                forward.lose(problem)

    def refresh(self, context: str, since: float):
        """After a network change: rebuild the context's tunnels that are older than it."""
        for forward in self._forwards.values():
            if forward.context_key == context and since:
                forward.refresh(since)

    def hurry(self, context: str):
        for forward in self._forwards.values():
            if forward.context_key == context:
                forward.hurry()

    # ------------------------------------------------------------ queries

    def contexts_in_use(self) -> set:
        """Contexts of forwards that should be running, for the cluster watchdog."""
        return {f.context_key for f in self._forwards.values() if f.desired and f.state in ACTIVE}

    def get(self, sid):
        return self._forwards.get(sid)

    def desired_ids(self):
        return [sid for sid, forward in self._forwards.items() if forward.desired]

    def failed_ids(self):
        return [
            sid
            for sid, forward in self._forwards.items()
            if forward.state in (State.ERROR, State.RETRYING)
        ]

    def snapshot(self) -> dict:
        return {sid: forward.snapshot() for sid, forward in self._forwards.items()}

    def counts(self) -> Counter:
        return Counter(str(forward.state) for forward in self._forwards.values())

    # ------------------------------------------------------------ exit

    def shutdown(self, timeout_ms: int = 2500):
        """Stop every kubectl process before the application exits."""
        processes = [p for p in (f.terminate_for_exit() for f in self._forwards.values()) if p]
        for process in processes:
            if not process.waitForFinished(timeout_ms // max(1, len(processes))):
                process.kill()
                process.waitForFinished(300)
        return len(processes)
