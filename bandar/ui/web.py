"""WebEngine policy: bundled files only, external links open in the browser."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineUrlRequestInterceptor
from PySide6.QtWebEngineWidgets import QWebEngineView

from bandar.resources import WEB

log = logging.getLogger(__name__)
_LEVELS = {
    QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: logging.ERROR,
    QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: logging.WARNING,
}


class LocalOnly(QWebEngineUrlRequestInterceptor):
    """Block every request that is not a bundled asset or the WebChannel script."""

    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() in {"qrc", "data"}:
            return
        if url.isLocalFile() and Path(url.toLocalFile()).resolve().is_relative_to(WEB):
            return
        info.block(True)


class Page(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        log.log(_LEVELS.get(level, logging.INFO), "JS %s:%s %s", source, line, message[:4000])

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        if url.isLocalFile() and Path(url.toLocalFile()).resolve() == WEB / "index.html":
            return True
        clicked = navigation_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked
        if clicked and url.scheme() in {"https", "http"}:
            QDesktopServices.openUrl(url)
        return False


class View(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
