"""Application service: the single entry point for every user intention.

The interface never edits configuration or processes directly. It asks the
Application, which validates against the domain rules, updates the runtime,
persists the result and announces the change. Slow work (port ownership, kubectl
lookups, file writes) is asynchronous; such methods receive a ``respond`` callback.
"""

from __future__ import annotations

import copy
import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

from bandar import VERSION
from bandar.core import config as cfg
from bandar.core import ports
from bandar.core.commands import (
    CommandError,
    apply_import,
    display_command,
    export_text,
    parse_kubectl,
    plan_import,
)
from bandar.infra.kube import KubeClient
from bandar.infra.store import ConfigStore
from bandar.runtime.forward import COMMAND_FIELDS, State
from bandar.runtime.manager import ForwardManager
from bandar.runtime.tasks import TaskRunner
from bandar.runtime.watchdog import ClusterWatchdog

log = logging.getLogger(__name__)
CONTEXT_REFRESH_MS = 60_000
UNGROUPED = "__ungrouped__"


class Application(QObject):
    stateChanged = Signal()
    logLine = Signal(str, object)
    notice = Signal(object)  # {"level", "code", ...params}; translated by the UI

    def __init__(self, config_path: Path, parent=None):
        super().__init__(parent)
        self.tasks = TaskRunner(parent=self)
        self.store = ConfigStore(config_path, self.tasks, self)
        self.config, self.config_notice = self.store.load()
        self.kube = KubeClient(self.settings, self)
        self.kube_info = {
            "current": "",
            "contexts": [],
            "error": None,
            "version": "",
            "unreachable": [],
        }
        self.manager = ForwardManager(self.settings, self.tasks, self.current_context, self)
        self.manager.sync(self.config["services"])
        self.manager.changed.connect(self._runtime_changed)
        self.manager.logged.connect(self.logLine)
        self.manager.failed.connect(self._forward_failed)
        self.manager.recovered.connect(self._forward_recovered)
        self.watchdog = ClusterWatchdog(self.manager, self.settings, self)
        self.watchdog.checked.connect(self._cluster_checked)
        self.store.externalChange.connect(self._external_change)
        self.store.externalInvalid.connect(self._external_invalid)
        self.store.saveFailed.connect(
            lambda error: self._notify("error", "save_failed", detail=error)
        )
        self._context_timer = QTimer(self)
        self._context_timer.timeout.connect(self.refresh_contexts)

    # ------------------------------------------------------------ lifecycle

    def settings(self) -> dict:
        return self.config["settings"]

    def current_context(self) -> str:
        return self.kube_info["current"]

    def boot(self):
        """Discover kube contexts and resume forwards. Called once the UI is listening."""
        if not self.store.path.exists():
            self.store.save(self.config)  # create the file so it can be found and edited
        self.refresh_contexts()
        self._context_timer.start(CONTEXT_REFRESH_MS)
        self.watchdog.start()
        self.kube.query("version", {}, self._version_known)
        if self.config_notice:
            self._notify("error", self.config_notice["code"], detail=self.config_notice["detail"])
        resume = [s["id"] for s in self.config["services"] if s["autoStart"]]
        if self.settings()["startup"] == "restore":
            resume += self.config["session"]["running"]
        if resume:
            self.manager.start(resume)

    def shutdown(self):
        self._context_timer.stop()
        self.watchdog.stop()
        self.kube.shutdown()
        stopped = self.manager.shutdown()
        self.tasks.shutdown(wait=True)
        self.store.flush(self.config)
        log.info("Shut down; stopped %d kubectl processes", stopped)

    # ------------------------------------------------------------ snapshots

    def snapshot(self) -> dict:
        return {
            "config": self.config,
            "runtime": self.manager.snapshot(),
            "meta": {
                "version": VERSION,
                "configPath": str(self.store.path),
                "readOnly": self.store.read_only,
                "configError": self.config_notice["detail"] if self.config_notice else "",
                "kube": self.kube_info,
                "kubeconfig": str(cfg.kubeconfig_path(self.settings())),
            },
        }

    def counts(self):
        return self.manager.counts()

    # ------------------------------------------------------------ services

    def save_service(self, params, respond):
        """Validate, check the local port on this machine, then commit."""
        editing = params.get("id") or None
        data = params.get("data") or {}
        service, errors = cfg.validate_service(data, self.config, editing)
        if errors:
            respond({"ok": False, "errors": errors})
            return
        forward = self.manager.get(editing) if editing else None
        holds_port = bool(
            forward
            and forward.desired
            and forward.service["localPort"] == service["localPort"]
            and forward.service["address"] == service["address"]
        )
        if holds_port:
            self._commit_service(service, params, respond)
            return

        def checked(result):
            if isinstance(result, Exception):
                result = {"status": "free"}
            if result["status"] != "free":
                error = {"code": f"port_{result['status']}", "owner": result.get("owner")}
                respond({"ok": False, "errors": {"localPort": error}})
                return
            # Re-validate: the configuration may have changed while the port was probed.
            fresh, late_errors = cfg.validate_service(data, self.config, editing)
            if late_errors:
                respond({"ok": False, "errors": late_errors})
                return
            fresh["id"] = service["id"]
            self._commit_service(fresh, params, respond)

        self.tasks.run(_port_report, service["localPort"], service["address"], callback=checked)

    def _commit_service(self, service, params, respond):
        """Store the service; ``start`` means "make it run the new configuration now"."""
        config = copy.deepcopy(self.config)
        index = next(
            (i for i, s in enumerate(config["services"]) if s["id"] == service["id"]), None
        )
        previous = config["services"][index] if index is not None else None
        if index is None:
            config["services"].append(service)
        else:
            config["services"][index] = service
        forward = self.manager.get(service["id"])
        was_active = bool(forward and forward.desired)
        command_changed = previous is not None and any(
            previous.get(key) != service.get(key) for key in COMMAND_FIELDS
        )
        self._commit(config)  # an active forward with a changed command reconnects here
        if params.get("start"):
            if not was_active:
                self.manager.start([service["id"]])
            elif not command_changed:
                self.manager.restart([service["id"]])
        respond({"ok": True, "id": service["id"]})

    def delete_services(self, params):
        ids = set(params.get("ids") or [])
        config = copy.deepcopy(self.config)
        config["services"] = [s for s in config["services"] if s["id"] not in ids]
        self._commit(config)
        return {"ok": True, "deleted": len(ids)}

    def duplicate_service(self, params):
        source = self._service(params.get("id"))
        if not source:
            return {"ok": False}
        config = copy.deepcopy(self.config)
        taken_ports = {s["localPort"] for s in config["services"]}
        port = source["localPort"] + 1
        while port in taken_ports or port > 65535:
            port = port + 1 if port < 65535 else 1024
        clone = {
            **copy.deepcopy(source),
            "id": cfg.new_id("s", {s["id"] for s in config["services"]}),
            "name": cfg.unique_name(
                f"{source['name']}-copy", [s["name"] for s in config["services"]]
            ),
            "localPort": port,
            "autoStart": False,
        }
        position = config["services"].index(
            next(s for s in config["services"] if s["id"] == source["id"])
        )
        config["services"].insert(position + 1, clone)
        self._commit(config)
        return {"ok": True, "id": clone["id"]}

    def move_service(self, params):
        """Drag and drop: put ``id`` into ``group`` in front of ``before`` (or last)."""
        sid = params.get("id")
        group = self._group_id(params.get("group"))
        if not self._service(sid) or group is None:
            return {"ok": False}
        config = copy.deepcopy(self.config)
        for service in config["services"]:
            if service["id"] == sid:
                service["group"] = group
        config["services"] = cfg.move_before(config["services"], sid, params.get("before"))
        self._commit(config)
        return {"ok": True}

    def assign_group(self, params):
        group = self._group_id(params.get("group"))
        if group is None:
            return {"ok": False}
        ids = set(params.get("ids") or [])
        config = copy.deepcopy(self.config)
        for service in config["services"]:
            if service["id"] in ids:
                service["group"] = group
        self._commit(config)
        return {"ok": True}

    def sort_services(self, params):
        """Sort one group's services by name (``group`` = id, ``__ungrouped__`` or all)."""
        group = params.get("group")
        config = copy.deepcopy(self.config)
        if group is None:
            ids = None
        else:
            wanted = "" if group == UNGROUPED else group
            ids = {s["id"] for s in config["services"] if s["group"] == wanted}
        config["services"] = cfg.sorted_by_name(config["services"], ids)
        self._commit(config)
        return {"ok": True}

    def pin(self, params):
        """Pin or unpin services and groups; pinned items gather in the "Pinned" view."""
        pinned = params.get("pinned") is True
        services = set(params.get("services") or [])
        groups = set(params.get("groups") or [])
        config = copy.deepcopy(self.config)
        for item in config["services"]:
            if item["id"] in services:
                item["pinned"] = pinned
        for item in config["groups"]:
            if item["id"] in groups:
                item["pinned"] = pinned
        self._commit(config, sync=False)
        return {"ok": True}

    # ------------------------------------------------------------ groups

    def save_group(self, params):
        editing = params.get("id") or None
        group, errors = cfg.validate_group(params.get("data") or {}, self.config, editing)
        if errors:
            return {"ok": False, "errors": errors}
        config = copy.deepcopy(self.config)
        index = next((i for i, g in enumerate(config["groups"]) if g["id"] == group["id"]), None)
        if index is None:
            config["groups"].append(group)
        else:
            config["groups"][index] = group
        members = params.get("services")
        if isinstance(members, list):
            members = set(members)
            for service in config["services"]:
                if service["id"] in members:
                    service["group"] = group["id"]
                elif service["group"] == group["id"]:
                    service["group"] = ""
        self._commit(config)
        return {"ok": True, "id": group["id"]}

    def delete_group(self, params):
        gid = params.get("id")
        config = copy.deepcopy(self.config)
        members = {s["id"] for s in config["services"] if s["group"] == gid}
        config["groups"] = [g for g in config["groups"] if g["id"] != gid]
        if params.get("withServices"):
            config["services"] = [s for s in config["services"] if s["id"] not in members]
        else:
            for service in config["services"]:
                if service["id"] in members:
                    service["group"] = ""
        self._commit(config)
        return {"ok": True}

    def move_group(self, params):
        config = copy.deepcopy(self.config)
        config["groups"] = cfg.move_before(config["groups"], params.get("id"), params.get("before"))
        self._commit(config)
        return {"ok": True}

    def sort_groups(self, _params):
        config = copy.deepcopy(self.config)
        config["groups"] = cfg.sorted_by_name(config["groups"])
        self._commit(config)
        return {"ok": True}

    def collapse_group(self, params):
        config = copy.deepcopy(self.config)
        for group in config["groups"]:
            if group["id"] == params.get("id"):
                group["collapsed"] = params.get("collapsed") is True
        self._commit(config, sync=False)
        return {"ok": True}

    # ------------------------------------------------------------ forwards

    def start(self, params):
        self.manager.start(self._ids(params))
        self._remember_session()
        return {"ok": True}

    def stop(self, params):
        self.manager.stop(self._ids(params))
        self._remember_session()
        return {"ok": True}

    def restart(self, params):
        self.manager.restart(self._ids(params))
        self._remember_session()
        return {"ok": True}

    def retry_failed(self, _params):
        ids = self.manager.failed_ids()
        self.manager.restart(ids)
        return {"ok": True, "count": len(ids)}

    def logs(self, params):
        forward = self.manager.get(params.get("id"))
        return {"ok": bool(forward), "logs": list(forward.logs) if forward else []}

    def clear_logs(self, params):
        forward = self.manager.get(params.get("id"))
        if forward:
            forward.clear_logs()
        return {"ok": True}

    def release_port(self, params, respond):
        """Stop a leftover kubectl that holds a service's port, then retry the service."""
        service = self._service(params.get("id"))
        if not service:
            respond({"ok": False})
            return

        def released(result):
            if isinstance(result, Exception):
                result = {"ok": False, "code": "unknown", "detail": str(result)}
            if result.get("ok"):
                QTimer.singleShot(600, lambda: self.manager.restart([service["id"]]))
            respond(result)

        self.tasks.run(ports.release, service["localPort"], callback=released)

    # ------------------------------------------------------------ ports and commands

    def check_port(self, params, respond):
        """Live form feedback: who owns ``port``, in the config and on this machine."""
        port = cfg.parse_port(params.get("port"))
        address = params.get("address") or "127.0.0.1"
        exclude = params.get("exclude") or None
        if port is None or not cfg.valid_address(address):
            respond({"status": "invalid"})
            return
        holder = cfg.port_holder(self.config["services"], port, address, exclude)
        if holder:
            respond({"status": "taken", "service": holder["name"]})
            return
        forward = self.manager.get(exclude) if exclude else None
        if forward and forward.desired and forward.service["localPort"] == port:
            respond({"status": "own"})
            return
        self.tasks.run(
            _port_report,
            port,
            address,
            callback=lambda result: respond(
                {"status": "free"} if isinstance(result, Exception) else result
            ),
        )

    def suggest_port(self, params, respond):
        preferred = cfg.parse_port(params.get("preferred")) or 10000
        address = params.get("address") or "127.0.0.1"
        exclude = params.get("exclude")
        taken = {s["localPort"] for s in self.config["services"] if s["id"] != exclude}
        self.tasks.run(
            ports.suggest,
            preferred,
            taken,
            address,
            callback=lambda port: respond({"port": 0 if isinstance(port, Exception) else port}),
        )

    def parse_command(self, params):
        try:
            return {"ok": True, "fields": parse_kubectl(params.get("text") or "")}
        except CommandError as error:
            return {"ok": False, "error": error.as_dict()}

    def preview_command(self, params):
        """The kubectl command a (possibly incomplete) form would run."""
        data = params.get("data") or {}
        extra = data.get("extraArgs")
        service = {
            "context": cfg.clean_text(data.get("context"), 253),
            "namespace": cfg.clean_text(data.get("namespace"), 63),
            "kind": cfg.KIND_ALIASES.get(str(data.get("kind", "")).lower(), "service"),
            "target": cfg.clean_text(data.get("target"), 253) or "<name>",
            "localPort": cfg.parse_port(data.get("localPort")) or "<local>",
            "remotePort": cfg.parse_remote_port(data.get("remotePort")) or "<remote>",
            "address": cfg.clean_text(data.get("address"), 200) or "127.0.0.1",
            "extraArgs": extra if isinstance(extra, list) else [],
        }
        text = display_command(service, self.settings())
        if isinstance(extra, str) and extra.strip():
            text += " " + extra.strip()
        return {"command": text}

    def preview_import(self, params):
        plan = plan_import(params.get("text") or "", self.config, params.get("update") is not False)
        return plan.as_dict()

    def apply_import(self, params):
        plan = plan_import(params.get("text") or "", self.config, params.get("update") is not False)
        config, changed = apply_import(plan, self.config)
        self._commit(config)
        return {"ok": True, "summary": plan.summary(), "changed": changed}

    def export(self, params):
        ids = params.get("ids")
        chosen = set(ids) if isinstance(ids, list) else None
        return {"text": export_text(self.config, chosen, header=f"Bandar {VERSION} export")}

    # ------------------------------------------------------------ settings and kube

    def update_settings(self, params):
        config = copy.deepcopy(self.config)
        config["settings"] = cfg.normalize_settings({**config["settings"], **(params or {})})
        if (
            config["settings"]["clusterCheckInterval"]
            != self.config["settings"]["clusterCheckInterval"]
        ):
            QTimer.singleShot(0, self.watchdog.apply_settings)
        tooling = ("kubectl", "kubeconfig")
        if any(config["settings"][k] != self.config["settings"][k] for k in tooling):
            self.kube.invalidate()
            QTimer.singleShot(0, self.refresh_contexts)
        self._commit(config, sync=False)
        return {"ok": True, "settings": config["settings"]}

    def kube_query(self, params, respond):
        self.kube.query(params.get("op", ""), params, respond)

    def use_context(self, params, respond):
        """Make ``name`` kubectl's current context, then re-read the kubeconfig."""
        name = cfg.clean_text(params.get("name"), 253)
        known = {c["name"] for c in self.kube_info["contexts"]}
        if not name or (known and name not in known):
            respond({"ok": False, "error": {"code": "context_missing", "detail": name}})
            return

        def switched(result):
            if result["ok"]:
                log.info("Current kubectl context switched to %s", name)
                self.kube_info["current"] = name
                self.refresh_contexts()
            respond(result)

        self.kube.use_context(name, switched)

    def refresh_contexts(self, _params=None):
        self.kube.query("contexts", {}, self._contexts_known)
        return {"ok": True}

    def _contexts_known(self, result):
        if result["ok"]:
            self.kube_info.update(result["data"], error=None)
        else:
            self.kube_info["error"] = result["error"]
        self.stateChanged.emit()

    def _version_known(self, result):
        if result["ok"]:
            self.kube_info["version"] = (result["data"].get("clientVersion") or {}).get(
                "gitVersion", ""
            )
            self.stateChanged.emit()

    def reset_config(self, _params):
        moved = self.store.reset()
        self.config_notice = None
        self.store.save(self.config)
        self.stateChanged.emit()
        return {"ok": True, "backup": str(moved) if moved else ""}

    # ------------------------------------------------------------ internals

    def _commit(self, config, sync=True):
        self.config = cfg.normalize(config)
        self.config["session"]["running"] = self.manager.desired_ids()
        if sync:
            self.manager.sync(self.config["services"])
            self.config["session"]["running"] = self.manager.desired_ids()
        self.store.save(self.config)
        self.stateChanged.emit()

    def _runtime_changed(self):
        self._remember_session()
        self.stateChanged.emit()

    def _remember_session(self):
        """Persist which services should run, so the next launch can resume them."""
        running = [sid for sid in self.manager.desired_ids() if self._service(sid)]
        if running != self.config["session"]["running"]:
            self.config["session"]["running"] = running
            self.store.save(self.config)

    def _forward_failed(self, sid, snapshot):
        """Announce a failure once: when it stops for good, or when a tunnel first drops."""
        service = self._service(sid)
        first_failure = snapshot["state"] == State.RETRYING and snapshot["attempt"] == 1
        if not service or not (snapshot["state"] == State.ERROR or first_failure):
            return
        if snapshot["state"] == State.RETRYING:
            kind = "lost"
        elif not snapshot["restarts"] and not snapshot["lastError"]:
            kind = "failed"  # it never came up
        else:
            kind = "error"
        self._notify(
            "error" if snapshot["state"] == State.ERROR else "warn",
            "forward_failed",
            service=service["name"],
            id=sid,
            error=snapshot["error"],
            state=snapshot["state"],
            kind=kind,
        )

    def _cluster_checked(self, _context, _reachable, _problem):
        unreachable = sorted(self.watchdog.unreachable)
        if unreachable != self.kube_info["unreachable"]:
            self.kube_info["unreachable"] = unreachable
            self.stateChanged.emit()

    def _forward_recovered(self, sid, snapshot):
        service = self._service(sid)
        if service:
            self._notify(
                "ok",
                "forward_recovered",
                service=service["name"],
                id=sid,
                error=snapshot["lastError"],
            )

    def _external_change(self, config):
        self.config = config
        self.config_notice = None
        self.manager.sync(self.config["services"])
        self.config["session"]["running"] = [
            sid for sid in self.manager.desired_ids() if self._service(sid)
        ]
        self._notify("info", "config_reloaded")
        self.stateChanged.emit()

    def _external_invalid(self, detail):
        self.config_notice = {"code": "config_invalid", "detail": detail, "readOnly": True}
        self._notify("error", "config_invalid", detail=detail)
        self.stateChanged.emit()

    def _notify(self, level, code, **params):
        self.notice.emit({"level": level, "code": code, **params})

    def _service(self, sid):
        return next((s for s in self.config["services"] if s["id"] == sid), None)

    def _group_id(self, value):
        """``""``/``__ungrouped__`` → ungrouped, a known id → itself, else ``None``."""
        if value in ("", None, UNGROUPED):
            return ""
        return value if any(g["id"] == value for g in self.config["groups"]) else None

    def _ids(self, params):
        ids = params.get("ids")
        return [sid for sid in ids if isinstance(sid, str)] if isinstance(ids, list) else []


def _port_report(port: int, address: str) -> dict:
    """Worker thread: bind status plus, when busy, the owning process."""
    status = ports.status(port, address)
    report = {"status": status}
    if status == "busy":
        report["owner"] = ports.owner(port)
    return report
