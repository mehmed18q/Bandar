"""Desktop notifications for forwards that drop, fail or recover.

Notifications go through the freedesktop service via ``notify-send`` (with
action buttons), so they work on desktops without a tray, such as stock GNOME.
The tray balloon is the fallback. Each notification runs as its own QProcess,
so nothing blocks; a clicked action is reported back through ``activated``.
"""

from __future__ import annotations

import shutil
import time

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from bandar import APP_ID, APP_NAME
from bandar.resources import ICON

THROTTLE_SECONDS = 20  # at most one notification per service and kind in this window
ACTION_WAIT_MS = 120_000  # stop waiting for a click after two minutes

TEXT = {
    "en": {
        "lost": "Connection lost, reconnecting…",
        "failed": "Failed to start",
        "error": "Stopped with an error",
        "recovered": "Reconnected",
        "many": "{n} services",
        "unreachable": "Cannot reach the cluster. Check your VPN or network.",
        "retry": "Retry",
        "show": "Show",
    },
    "fa": {
        "lost": "اتصال قطع شد؛ در حال اتصال دوباره…",
        "failed": "اجرا نشد",
        "error": "با خطا متوقف شد",
        "recovered": "دوباره وصل شد",
        "many": "{n} سرویس",
        "unreachable": "دسترسی به کلاستر ممکن نیست؛ VPN یا شبکه را بررسی کنید.",
        "retry": "تلاش دوباره",
        "show": "نمایش",
    },
    "ar": {
        "lost": "انقطع الاتصال، جارٍ إعادة الاتصال…",
        "failed": "تعذّر التشغيل",
        "error": "توقّف بسبب خطأ",
        "recovered": "أُعيد الاتصال",
        "many": "{n} خدمات",
        "unreachable": "تعذّر الوصول إلى العنقود. تحقّق من VPN أو الشبكة.",
        "retry": "إعادة المحاولة",
        "show": "عرض",
    },
}


def text(language: str, key: str) -> str:
    return TEXT.get(language, TEXT["en"])[key]


class Notifier(QObject):
    activated = Signal(list, str)  # service ids, action ("retry" | "show")

    def __init__(self, tray=None, parent=None, program=None):
        super().__init__(parent)
        self._tray = tray
        self._program = program if program is not None else shutil.which("notify-send")
        self._recent = {}
        self._processes = set()

    @property
    def pending(self) -> int:
        """Notifications still waiting for a click or to expire."""
        return len(self._processes)

    @property
    def available(self) -> bool:
        return bool(self._program or self._tray)

    def notify(self, ids, kind, title, body, language="en", urgency="normal"):
        """Show one notification about ``ids``; the same kind for the same services is throttled."""
        ids = [ids] if isinstance(ids, str) else list(ids)
        key = (tuple(sorted(ids)), kind)
        now = time.monotonic()
        if now - self._recent.get(key, -THROTTLE_SECONDS) < THROTTLE_SECONDS:
            return False
        self._recent[key] = now
        if self._program:
            self._send(ids, kind, title, body, language, urgency)
            return True
        if self._tray:
            self._tray.notify(title, body, error=urgency == "critical")
            return True
        return False

    def _send(self, ids, kind, title, body, language, urgency):
        args = [
            f"--app-name={APP_NAME}",
            f"--icon={ICON}",
            f"--urgency={urgency}",
            f"--hint=string:desktop-entry:{APP_ID}",
            "--expire-time=10000",
            f"--action=default={text(language, 'show')}",
        ]
        if kind not in {"recovered", "background"}:
            args.append(f"--action=retry={text(language, 'retry')}")
        args += [title, body[:400]]
        process = QProcess(self)
        self._processes.add(process)
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.timeout.connect(process.kill)

        def finished(*_):
            choice = bytes(process.readAllStandardOutput().data()).decode(errors="ignore").strip()
            self._processes.discard(process)
            process.deleteLater()
            if choice in {"default", "retry"}:
                self.activated.emit(ids, "retry" if choice == "retry" else "show")

        process.finished.connect(finished)
        process.errorOccurred.connect(
            lambda error: error == QProcess.ProcessError.FailedToStart and finished()
        )
        process.start(self._program, args)
        timer.start(ACTION_WAIT_MS)

    def shutdown(self):
        """Close pending notifications without reporting them (application exit)."""
        for process in list(self._processes):
            process.finished.disconnect()
            process.kill()
            process.waitForFinished(200)
            process.deleteLater()
        self._processes.clear()
