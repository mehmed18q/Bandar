"""Asynchronous, cached kubectl lookups for form suggestions and context display.

Every query is a short-lived QProcess with a deadline, so a slow or unreachable
cluster never freezes the interface. Identical concurrent queries share one
process, and results are cached for a short time.
"""

from __future__ import annotations

import json
import time
from functools import partial

from PySide6.QtCore import QObject, QProcess, QTimer

from bandar.core.diagnostics import Problem, classify

TIMEOUT_MS = 15_000
RESOURCE = {
    "service": "services",
    "pod": "pods",
    "deployment": "deployments",
    "statefulset": "statefulsets",
    "replicaset": "replicasets",
}
_CONTAINER_PORTS = (
    '{range .spec.containers[*]}{range .ports[*]}{.containerPort}{"/"}{.name}{" "}{end}{end}'
)
JSONPATH = {
    "service": '{range .items[*]}{.metadata.name}{"\\t"}'
    '{range .spec.ports[*]}{.port}{"/"}{.name}{" "}{end}{"\\n"}{end}',
    "pod": '{range .items[*]}{.metadata.name}{"\\t"}' + _CONTAINER_PORTS + '{"\\n"}{end}',
    "workload": '{range .items[*]}{.metadata.name}{"\\t"}'
    + _CONTAINER_PORTS.replace(".spec.containers", ".spec.template.spec.containers")
    + '{"\\n"}{end}',
}
TTL = {"contexts": 8, "namespaces": 120, "targets": 30, "version": 3600}


def parse_targets(text: str) -> list:
    """``name\\tport/name port/name`` lines → ``[{name, ports: [{port, name}]}]``."""
    items = []
    for line in text.splitlines():
        name, _, ports = line.partition("\t")
        if not name.strip():
            continue
        found, seen = [], set()
        for token in ports.split():
            number, _, port_name = token.partition("/")
            if number.isdigit() and number not in seen:
                seen.add(number)
                found.append({"port": int(number), "name": port_name})
        items.append({"name": name.strip(), "ports": found})
    return sorted(items, key=lambda item: item["name"])


def parse_contexts(text: str) -> dict:
    data = json.loads(text or "{}")
    contexts = []
    for entry in data.get("contexts") or []:
        details = entry.get("context") or {}
        contexts.append(
            {
                "name": entry.get("name", ""),
                "cluster": details.get("cluster", ""),
                "namespace": details.get("namespace", ""),
            }
        )
    return {"current": data.get("current-context", ""), "contexts": contexts}


class KubeClient(QObject):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._cache = {}
        self._waiting = {}

    def invalidate(self):
        self._cache.clear()

    def query(self, op: str, params: dict, callback):
        """Run ``op`` and call ``callback({"ok": bool, "data"|"error": ...})`` later.

        The callback always runs from the event loop, never synchronously.
        """
        try:
            key, args, parser = self._plan(op, params or {})
        except (KeyError, ValueError):
            QTimer.singleShot(
                0, lambda: callback({"ok": False, "error": {"code": "invalid_query"}})
            )
            return
        cached = self._cache.get(key)
        if cached and time.monotonic() - cached[0] < TTL[op]:
            QTimer.singleShot(0, lambda: callback(cached[1]))
            return
        if key in self._waiting:
            self._waiting[key].append(callback)
            return
        self._waiting[key] = [callback]
        self._run(key, op, args, parser)

    def use_context(self, name: str, callback):
        """``kubectl config use-context NAME``: changes kubectl's current context globally."""
        settings = self._settings()
        base = ["--kubeconfig", settings["kubeconfig"]] if settings.get("kubeconfig") else []
        key = ("use-context", name)
        if key in self._waiting:
            self._waiting[key].append(callback)
            return
        self._waiting[key] = [callback]

        def done(text):
            self.invalidate()
            return text.strip()

        self._run(key, "use-context", [*base, "config", "use-context", name], done, cache=False)

    def _plan(self, op, params):
        settings = self._settings()
        base = ["--kubeconfig", settings["kubeconfig"]] if settings.get("kubeconfig") else []
        context = params.get("context") or ""
        scope = base + (["--context", context] if context else [])
        if op == "contexts":
            return (op,), base + ["config", "view", "-o", "json"], parse_contexts
        if op == "version":
            return (op,), ["version", "--client", "-o", "json"], json.loads
        if op == "namespaces":
            args = scope + ["get", "namespaces", "-o", "jsonpath={.items[*].metadata.name}"]
            args.append("--request-timeout=10s")
            return (op, context), args, lambda text: sorted(text.split())
        if op == "targets":
            kind = params["kind"]
            namespace = params.get("namespace") or ""
            template = JSONPATH.get(kind, JSONPATH["workload"])
            args = scope + (["--namespace", namespace] if namespace else [])
            args += ["get", RESOURCE[kind], "-o", f"jsonpath={template}", "--request-timeout=10s"]
            return (op, context, namespace, kind), args, parse_targets
        raise KeyError(op)

    def _run(self, key, op, args, parser, cache=True):
        process = QProcess(self)
        deadline = QTimer(process)
        deadline.setSingleShot(True)
        deadline.timeout.connect(process.kill)
        process.setProgram(self._settings()["kubectl"])
        process.setArguments(args)
        process.finished.connect(partial(self._finished, process, key, parser, deadline, cache))
        process.errorOccurred.connect(partial(self._error, process, key))
        process.start()
        deadline.start(TIMEOUT_MS)

    def _finished(self, process, key, parser, deadline, cache, code, _status):
        timed_out = not deadline.isActive()
        deadline.stop()
        output = bytes(process.readAllStandardOutput().data()).decode(errors="replace")
        errors = bytes(process.readAllStandardError().data()).decode(errors="replace")
        process.deleteLater()
        if timed_out:
            result = {"ok": False, "error": Problem("timeout", True, "kubectl timed out").as_dict()}
        elif code != 0:
            result = {"ok": False, "error": classify(errors or output).as_dict()}
        else:
            try:
                result = {"ok": True, "data": parser(output)}
            except (ValueError, TypeError) as failure:
                result = {"ok": False, "error": Problem("unknown", True, str(failure)).as_dict()}
            if cache:
                self._cache[key] = (time.monotonic(), result)
        self._deliver(key, result)

    def _error(self, process, key, error):
        if error != QProcess.ProcessError.FailedToStart:
            return
        detail = f"{process.program()}: {process.errorString()}"
        process.deleteLater()
        self._deliver(
            key, {"ok": False, "error": Problem("kubectl_missing", False, detail).as_dict()}
        )

    def _deliver(self, key, result):
        for callback in self._waiting.pop(key, []):
            callback(result)
