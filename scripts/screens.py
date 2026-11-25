"""Render the real window offscreen and save screenshots of chosen scenes.

    .venv/bin/python scripts/screens.py OUTPUT_DIR [scene ...]

Each scene is JavaScript run in the page before the screenshot. Uses the fake
kubectl and a temporary configuration, so it never touches a cluster.
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from bandar.app import Application  # noqa: E402
from bandar.core import config as cfg  # noqa: E402
from bandar.core.commands import apply_import, plan_import  # noqa: E402
from bandar.ui.window import MainWindow  # noqa: E402

LIST = (ROOT / "tests" / "fixtures" / "sample-services.txt").read_text()
RESET = (
    "document.querySelectorAll('dialog[open]').forEach(d => d.close());"
    "bandar.Overlays.Menu.close(); bandar.closePopovers && bandar.closePopovers();"
)
SCENES = {
    "main": "",
    "dark-fa": "bandar.actions.settings({theme:'dark', language:'fa'})",
    "ar": "bandar.actions.settings({theme:'light', language:'ar'})",
    "en": "bandar.actions.settings({theme:'light', language:'en'})",
    "dark": "bandar.actions.settings({theme:'dark', language:'en'})",
    "fa": "bandar.actions.settings({theme:'light', language:'fa'})",
    "group-new": "bandar.actions.newGroup()",
    "group-edit": "bandar.actions.editGroup(bandar.Store.state.config.groups[0].id)",
    "service-new": "bandar.actions.newService()",
    "theme-panel": "document.querySelector('#theme-settings-button').click()",
    "language-menu": "document.querySelector('#language-button').click()",
    "context-menu": "document.querySelector('#kube-note').click()",
    "settings": "bandar.actions.openSettings()",
    "import": "bandar.actions.openImport()",
    "drawer": "bandar.actions.details(bandar.Store.state.config.services[1].id)",
    "pinned": "bandar.Store.ui({view: 'pinned'})",
    "all": "bandar.Store.ui({view: 'all'})",
    "service-icons": "bandar.actions.editService(bandar.Store.state.config.services[2].id); setTimeout(() => document.querySelector('#service-dialog [data-icon-toggle]').click(), 300)",
}


def main():
    out = Path(sys.argv[1])
    scenes = sys.argv[2:] or ["main"]
    out.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp()) / "config.json"
    config = cfg.empty()
    config["settings"].update(
        kubectl=str(ROOT / "tests" / "fake_kubectl.py"),
        retryMaxDelay=2,
        closeAction="quit",
        theme="light",
    )
    config, _ = apply_import(plan_import(LIST, config), config)
    config["session"]["running"] = [s["id"] for s in config["services"]]
    config["services"][0]["pinned"] = True  # show a pin and the Pinned view
    config["groups"][0]["icon"] = "kubernetes"
    path.write_text(cfg.dumps(config))
    qt = QApplication.instance() or QApplication([])
    app = Application(path)
    window = MainWindow(app)
    window.resize(1500, 920)
    app.boot()
    delay = 3500
    for name in scenes:
        script = SCENES.get(name, name)
        QTimer.singleShot(delay, lambda s=script: window.page.runJavaScript(RESET + s))
        delay += 1300
        QTimer.singleShot(delay, lambda n=name: window.grab().save(str(out / f"{n}.png")))
        delay += 200
    QTimer.singleShot(delay + 200, window.request_quit)
    qt.exec()
    print("saved to", out)


if __name__ == "__main__":
    main()
