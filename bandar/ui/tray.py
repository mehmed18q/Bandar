"""System tray presence: forwards keep running while the window is hidden."""

from __future__ import annotations

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from bandar import APP_NAME
from bandar.resources import ICON

LABELS = {
    "en": {
        "show": "Show Bandar",
        "hide": "Hide window",
        "start": "Start all",
        "stop": "Stop all",
        "retry": "Retry failed",
        "quit": "Quit",
        "summary": "{healthy} healthy · {problems} problems · {total} services",
        "background": "Bandar keeps your port-forwards running in the background. Click the tray icon to show it.",
        "failed": "{service}: {state}",
    },
    "fa": {
        "show": "نمایش بندر",
        "hide": "پنهان کردن پنجره",
        "start": "اجرای همه",
        "stop": "توقف همه",
        "retry": "تلاش دوباره خطاها",
        "quit": "خروج",
        "summary": "{healthy} سالم · {problems} مشکل · {total} سرویس",
        "background": "بندر پورت‌فورواردها را در پس‌زمینه فعال نگه می‌دارد.",
        "failed": "{service}: {state}",
    },
    "ar": {
        "show": "إظهار بندر",
        "hide": "إخفاء النافذة",
        "start": "تشغيل الكل",
        "stop": "إيقاف الكل",
        "retry": "إعادة محاولة الأخطاء",
        "quit": "خروج",
        "summary": "{healthy} سليمة · {problems} مشكلات · {total} خدمات",
        "background": "يواصل بندر تشغيل إعادات توجيه المنافذ في الخلفية.",
        "failed": "{service}: {state}",
    },
}


class Tray(QSystemTrayIcon):
    def __init__(self, window):
        super().__init__(QIcon(str(ICON)), window)
        self.window = window
        self.language = "en"
        self.menu = QMenu()
        self.toggle_action = QAction(self.menu)
        self.toggle_action.triggered.connect(window.toggle_visible)
        self.start_action = QAction(self.menu)
        self.start_action.triggered.connect(window.start_all)
        self.stop_action = QAction(self.menu)
        self.stop_action.triggered.connect(window.stop_all)
        self.retry_action = QAction(self.menu)
        self.retry_action.triggered.connect(window.retry_failed)
        self.quit_action = QAction(self.menu)
        self.quit_action.triggered.connect(window.request_quit)
        for item in (
            self.toggle_action,
            None,
            self.start_action,
            self.stop_action,
            self.retry_action,
            None,
            self.quit_action,
        ):
            self.menu.addSeparator() if item is None else self.menu.addAction(item)
        self.menu.aboutToShow.connect(self.relabel)
        self.setContextMenu(self.menu)
        self.activated.connect(self._activated)
        self.relabel()

    @staticmethod
    def available() -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def text(self, key, **params):
        return LABELS.get(self.language, LABELS["en"])[key].format(**params)

    def relabel(self):
        visible = self.window.isVisible() and not self.window.isMinimized()
        self.toggle_action.setText(self.text("hide" if visible else "show"))
        self.start_action.setText(self.text("start"))
        self.stop_action.setText(self.text("stop"))
        self.retry_action.setText(self.text("retry"))
        self.quit_action.setText(self.text("quit"))

    def update_summary(self, counts, total):
        healthy = counts.get("healthy", 0)
        problems = counts.get("error", 0) + counts.get("retrying", 0)
        self.setToolTip(
            f"{APP_NAME}\n" + self.text("summary", healthy=healthy, problems=problems, total=total)
        )

    def notify(self, title, message, error=False):
        icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if error
            else QSystemTrayIcon.MessageIcon.Information
        )
        self.showMessage(title, message, icon, 6000)

    def _activated(self, reason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.window.toggle_visible()
