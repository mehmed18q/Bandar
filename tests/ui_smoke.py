"""Launch the real window offscreen with a fake kubectl, exercise it and take screenshots.

.venv/bin/python tests/ui_smoke.py [output-dir]
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWebEngineCore import QWebEnginePage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from bandar.app import Application  # noqa: E402
from bandar.core import config as cfg  # noqa: E402
from bandar.core.commands import apply_import, plan_import  # noqa: E402
from bandar.ui.window import MainWindow  # noqa: E402

LIST = """[orders @production]
orders-postgresql = kubectl --context main -n orders-api port-forward svc/ok-orders-psql 47432:5432
orders-redis = kubectl --context main -n orders-api port-forward svc/flaky-orders-redis 47379:6379
[chat-stage @staging]
chat-postgresql = kubectl --context prod -n chat port-forward svc/ok-chat-psql 47434:5432
chat-redis = kubectl --context prod -n chat port-forward svc/auth-chat-redis 47381:6379
[]
core-postgresql = kubectl port-forward svc/missing-core 47436:5432
"""


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.mkdtemp())
    path = home / "config.json"
    config = cfg.empty()
    config["settings"]["kubectl"] = str(ROOT / "tests" / "fake_kubectl.py")
    config["settings"]["retryMaxDelay"] = 2
    config["settings"]["closeAction"] = "quit"
    config, _ = apply_import(plan_import(LIST, config), config)
    config["session"]["running"] = [s["id"] for s in config["services"]]
    path.write_text(cfg.dumps(config))

    qt = QApplication.instance() or QApplication([])
    errors = []
    original = QWebEnginePage.javaScriptConsoleMessage

    def console(page, level, message, line, source):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            errors.append(f"{source}:{line}: {message}")
        return original(page, level, message, line, source)

    QWebEnginePage.javaScriptConsoleMessage = console
    app = Application(path)
    window = MainWindow(app)
    window.resize(1500, 920)
    app.boot()
    steps = [
        (3500, lambda: window.grab().save(str(out / "main-light.png"))),
        (
            200,
            lambda: window.page.runJavaScript(
                "bandar.actions.settings({theme:'dark', language:'fa'})"
            ),
        ),
        (1200, lambda: window.grab().save(str(out / "main-dark-fa.png"))),
        (
            200,
            lambda: window.page.runJavaScript(
                "bandar.actions.settings({theme:'light', language:'en'}); bandar.actions.newService()"
            ),
        ),
        (1500, lambda: window.grab().save(str(out / "service-form.png"))),
        (
            200,
            lambda: window.page.runJavaScript(
                "document.querySelector('#service-dialog').close(); bandar.actions.details(bandar.Store.state.config.services[1].id)"
            ),
        ),
        (1200, lambda: window.grab().save(str(out / "drawer.png"))),
        (
            100,
            lambda: window.page.runJavaScript(
                "JSON.stringify({rows: document.querySelectorAll('.service-row').length, groups: document.querySelectorAll('.group-row').length, problems: document.querySelectorAll('.problem').length})",
                lambda r: print("DOM", r),
            ),
        ),
        (500, lambda: window.request_quit()),
    ]
    delay = 0
    for wait, step in steps:
        delay += wait
        QTimer.singleShot(delay, step)
    qt.exec()
    states = {s["name"]: app.manager.get(s["id"]).state for s in app.config["services"]}
    print("STATES", json.dumps({k: str(v) for k, v in states.items()}))
    print("JS ERRORS", errors or "none")
    print("SCREENSHOTS", out)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
