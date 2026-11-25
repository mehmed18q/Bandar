"""The WebChannel adapter: JSON requests in, JSON replies and events out.

JavaScript sends ``{"id", "method", "params"}`` to ``request``. Each method is a
command routed to the Application (or to the window for shell concerns), and
its result returns through ``reply`` with the same id. Pushes (state, log lines,
notices) travel through ``event``. The bridge holds no business rules.
"""

from __future__ import annotations

import contextlib
import json
import logging

from PySide6.QtCore import Property, QObject, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication

from bandar import APP_NAME, AUTHOR, AUTHOR_URL, REPOSITORY, VERSION
from bandar import logs as app_logs
from bandar.core.config import kubeconfig_path

log = logging.getLogger(__name__)
STATE_PUSH_MS = 30


class Bridge(QObject):
    reply = Signal(str)
    event = Signal(str)

    def __init__(self, application, window, parent=None):
        super().__init__(parent)
        self.app = application
        self.window = window
        self._sync = {
            "state": lambda _params: application.snapshot(),
            "service.delete": application.delete_services,
            "service.duplicate": application.duplicate_service,
            "service.move": application.move_service,
            "service.assign": application.assign_group,
            "service.sort": application.sort_services,
            "pin.set": application.pin,
            "group.save": application.save_group,
            "group.delete": application.delete_group,
            "group.move": application.move_group,
            "group.sort": application.sort_groups,
            "group.collapse": application.collapse_group,
            "forward.start": application.start,
            "forward.stop": application.stop,
            "forward.restart": application.restart,
            "forward.retryFailed": application.retry_failed,
            "forward.logs": application.logs,
            "forward.clearLogs": application.clear_logs,
            "command.parse": application.parse_command,
            "command.preview": application.preview_command,
            "import.preview": application.preview_import,
            "import.apply": application.apply_import,
            "import.export": application.export,
            "settings.update": self._update_settings,
            "kube.refresh": application.refresh_contexts,
            "config.reset": application.reset_config,
            "shell.copy": self._copy,
            "shell.revealConfig": self._reveal_config,
            "shell.openLogs": self._open_logs,
            "shell.openUrl": self._open_url,
            "shell.openKubeconfig": self._open_kubeconfig,
            "shell.quit": lambda _params: window.request_quit() or {"ok": True},
            "shell.closeChoice": self._close_choice,
        }
        self._async = {
            "service.save": application.save_service,
            "port.check": application.check_port,
            "port.suggest": application.suggest_port,
            "port.release": application.release_port,
            "kube.query": application.kube_query,
            "kube.useContext": application.use_context,
        }
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.setInterval(STATE_PUSH_MS)
        self._state_timer.timeout.connect(self._push_state)
        application.stateChanged.connect(self._state_timer.start)
        application.logLine.connect(lambda sid, entry: self._emit("log", id=sid, entry=entry))
        application.notice.connect(lambda notice: self._emit("notice", notice=notice))

    @Property(str, constant=True)
    def appInfo(self):
        return json.dumps(
            {
                "name": APP_NAME,
                "version": VERSION,
                "author": AUTHOR,
                "authorUrl": AUTHOR_URL,
                "repository": REPOSITORY,
            }
        )

    @Slot(str)
    def request(self, text):
        try:
            message = json.loads(text)
            request_id = message["id"]
            method = message["method"]
            params = message.get("params") or {}
        except (ValueError, KeyError, TypeError):
            log.warning("Malformed request from the interface: %.200s", text)
            return

        def respond(result):
            self._reply(request_id, result)

        try:
            if method in self._sync:
                respond(self._sync[method](params))
            elif method in self._async:
                self._async[method](params, respond)
            else:
                respond({"ok": False, "error": {"code": "unknown_method", "method": method}})
        except Exception as error:
            log.exception("Request %s failed", method)
            respond({"ok": False, "error": {"code": "internal", "detail": str(error)}})

    # ------------------------------------------------------------ shell commands

    def _update_settings(self, params):
        result = self.app.update_settings(params)
        self.window.settings_changed(result["settings"])
        return result

    def _copy(self, params):
        QGuiApplication.clipboard().setText(str(params.get("text", "")))
        return {"ok": True}

    def _reveal_config(self, _params):
        folder = self.app.store.path.parent
        folder.mkdir(parents=True, exist_ok=True)
        return {"ok": QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))}

    def _open_logs(self, _params):
        folder = app_logs.directory()
        if not folder:
            return {"ok": False}
        return {"ok": QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))}

    def _open_kubeconfig(self, params):
        """Open the kubeconfig in the default editor, or its folder (``folder: true``)."""
        path = kubeconfig_path(self.app.settings())
        target = path.parent if params.get("folder") or not path.is_file() else path
        if not target.exists():
            return {"ok": False, "path": str(path)}
        return {
            "ok": QDesktopServices.openUrl(QUrl.fromLocalFile(str(target))),
            "path": str(target),
        }

    def _open_url(self, params):
        url = QUrl(str(params.get("url", "")))
        if url.scheme() not in {"https", "http"}:
            return {"ok": False}
        return {"ok": QDesktopServices.openUrl(url)}

    # ------------------------------------------------------------ outgoing

    def ask_close(self, **context):
        """Let the interface ask whether to keep running in the background or quit."""
        self._emit("close-request", **context)

    def _close_choice(self, params):
        choice = params.get("choice")
        if choice not in {"background", "quit"}:
            return {"ok": True}
        if params.get("remember"):
            self._update_settings({"closeAction": choice})
        QTimer.singleShot(
            0, self.window.to_background if choice == "background" else self.window.request_quit
        )
        return {"ok": True}

    def focus_service(self, sid):
        """Ask the interface to show one service's details (e.g. from a notification)."""
        self._emit("focus", id=sid)

    def _push_state(self):
        self._emit("state", state=self.app.snapshot())
        self.window.runtime_changed()

    def _reply(self, request_id, result):
        with contextlib.suppress(RuntimeError):  # the page closed while a reply was pending
            self.reply.emit(json.dumps({"id": request_id, "result": result}, default=str))

    def _emit(self, kind, **payload):
        self.event.emit(json.dumps({"type": kind, **payload}, default=str))
