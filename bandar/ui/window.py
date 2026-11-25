"""The main window: hosts the web interface, the tray icon and the exit sequence."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, QTimer, QUrl
from PySide6.QtGui import QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWidgets import QApplication, QMainWindow

from bandar import APP_NAME, VERSION
from bandar.resources import ICON, WEB
from bandar.ui.bridge import Bridge
from bandar.ui.notifier import Notifier, text
from bandar.ui.tray import Tray
from bandar.ui.web import LocalOnly, Page, View

log = logging.getLogger(__name__)
NOTICE_BATCH_MS = 1500  # failures arriving together are announced together


class MainWindow(QMainWindow):
    def __init__(self, application, hidden=False):
        super().__init__()
        self.app = application
        self.quitting = False
        self.told_about_tray = False
        self.setWindowTitle(f"{APP_NAME} {VERSION}")
        self.setWindowIcon(QIcon(str(ICON)))
        self.resize(1360, 860)
        self.setMinimumSize(940, 580)
        self.state = QSettings(
            str(application.store.path.parent / "window.ini"), QSettings.Format.IniFormat
        )
        if self.state.value("geometry"):
            self.restoreGeometry(self.state.value("geometry"))
        self.view = View(self)
        self.profile = QWebEngineProfile(self)  # off the record: no disk cache
        self.interceptor = LocalOnly(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        self.page = Page(self.profile, self.view)
        options = self.page.settings()
        options.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        options.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        options.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self.bridge = Bridge(application, self, self)
        self.channel = QWebChannel(self.page)
        self.channel.registerObject("native", self.bridge)
        self.page.setWebChannel(self.channel)
        self.tray = Tray(self) if Tray.available() else None
        if self.tray:
            self.tray.show()
        self.notifier = Notifier(self.tray, self)
        self._pending_notices = []
        self._notice_batch = QTimer(self)
        self._notice_batch.setSingleShot(True)
        self._notice_batch.setInterval(NOTICE_BATCH_MS)
        self._notice_batch.timeout.connect(self._flush_notices)
        self.notifier.activated.connect(self._notification_clicked)
        application.notice.connect(self._notice)
        self.settings_changed(application.settings())
        self.page_ready = False
        self.page.loadFinished.connect(lambda ok: setattr(self, "page_ready", ok))
        self.view.load(QUrl.fromLocalFile(str(WEB / "index.html")))
        if not (hidden and self.tray):
            self.show()

    # ------------------------------------------------------------ called by the bridge

    def settings_changed(self, settings):
        if self.tray:
            self.tray.language = settings["language"]
            self.tray.relabel()

    def runtime_changed(self):
        if self.tray:
            self.tray.update_summary(self.app.counts(), len(self.app.config["services"]))

    # ------------------------------------------------------------ tray commands

    def toggle_visible(self):
        if self.isVisible() and not self.isMinimized() and self.isActiveWindow():
            self.hide()
        else:
            self.bring_to_front()

    def bring_to_front(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def start_all(self):
        self.app.start({"ids": [s["id"] for s in self.app.config["services"]]})

    def stop_all(self):
        self.app.stop({"ids": [s["id"] for s in self.app.config["services"]]})

    def retry_failed(self):
        self.app.retry_failed({})

    # ------------------------------------------------------------ exit

    def closeEvent(self, event):
        if self.quitting:
            event.accept()
            return
        event.ignore()
        action = self.app.settings()["closeAction"]
        if action == "background":
            self.to_background()
        elif action == "quit" or not self.page_ready:
            self.request_quit()
        else:
            running = len(self.app.manager.desired_ids())
            self.bridge.ask_close(tray=bool(self.tray), running=running)

    def to_background(self):
        """Hide the window; forwards keep running. The tray or a new launch brings it back."""
        self._remember_geometry()
        self.hide()
        if not self.told_about_tray:
            self.told_about_tray = True
            language = self.app.settings()["language"]
            message = (self.tray.text("background") if self.tray else "") or ""
            self.notifier.notify(
                "app", "background", APP_NAME, message or APP_NAME, language, "low"
            )

    def request_quit(self):
        if self.quitting:
            return
        self.quitting = True
        self._remember_geometry()
        self.app.shutdown()
        self.notifier.shutdown()
        if self.tray:
            self.tray.hide()
        self.close()
        QApplication.quit()

    def _remember_geometry(self):
        self.state.setValue("geometry", self.saveGeometry())
        self.state.sync()

    def _notice(self, notice):
        """Queue failure/recovery notices; a burst (a VPN dropping) becomes one notification."""
        if notice.get("code") not in {"forward_failed", "forward_recovered"}:
            return
        mode = self.app.settings()["notifications"]
        if mode == "off" or (mode == "background" and self.isVisible() and self.isActiveWindow()):
            return
        self._pending_notices.append(notice)
        self._notice_batch.start()

    def _flush_notices(self):
        notices, self._pending_notices = self._pending_notices, []
        language = self.app.settings()["language"]
        by_kind = {}
        for notice in notices:
            kind = notice.get(
                "kind", "recovered" if notice["code"] == "forward_recovered" else "error"
            )
            by_kind.setdefault(kind, []).append(notice)
        for kind, group in by_kind.items():
            ids = list(dict.fromkeys(n["id"] for n in group))
            names = list(dict.fromkeys(n["service"] for n in group))
            codes = {
                (n.get("error") or {}).get("code") for n in group if n["code"] == "forward_failed"
            }
            headline = (
                text(language, "unreachable")
                if codes == {"api_unreachable"}
                else text(language, kind)
            )
            if len(ids) == 1:
                detail = (
                    (group[0].get("error") or {}).get("detail", "") if kind != "recovered" else ""
                )
                title, body = names[0], headline + (f"\n{detail}" if detail else "")
            else:
                shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
                title = text(language, "many").format(n=len(ids))
                body = f"{headline}\n{shown}"
            urgency = {"lost": "normal", "recovered": "low"}.get(kind, "critical")
            self.notifier.notify(ids, kind, title, body, language, urgency)

    def _notification_clicked(self, ids, action):
        if action == "retry":
            self.app.restart({"ids": ids})
        self.bring_to_front()
        if len(ids) == 1:
            self.bridge.focus_service(ids[0])
