"""The main window: hosts the web interface, the tray icon and the exit sequence."""

from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, QUrl
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
        """System notifications for forwards that drop, fail or come back."""
        code = notice.get("code")
        if code not in {"forward_failed", "forward_recovered"}:
            return
        mode = self.app.settings()["notifications"]
        focused = self.isVisible() and self.isActiveWindow()
        if mode == "off" or (mode == "background" and focused):
            return
        language = self.app.settings()["language"]
        kind = notice.get("kind", "recovered" if code == "forward_recovered" else "error")
        detail = (notice.get("error") or {}).get("detail", "") if code == "forward_failed" else ""
        body = text(language, kind) + (f"\n{detail}" if detail else "")
        urgency = {"lost": "normal", "recovered": "low"}.get(kind, "critical")
        self.notifier.notify(notice["id"], kind, notice["service"], body, language, urgency)

    def _notification_clicked(self, sid, action):
        if action == "retry":
            self.app.restart({"ids": [sid]})
        self.bring_to_front()
        self.bridge.focus_service(sid)
