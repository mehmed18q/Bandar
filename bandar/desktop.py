"""Command line entry point: parse arguments and compose the application."""

from __future__ import annotations

import argparse
import signal
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from bandar import APP_ID, APP_NAME, VERSION, logs
from bandar.core.config import default_path
from bandar.integration import register_source_run
from bandar.resources import ICON, PACKAGE


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="bandar", description=f"{APP_NAME}: a desktop manager for kubectl port-forwards"
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    parser.add_argument(
        "--config",
        type=Path,
        help="configuration file (default: $BANDAR_CONFIG or ~/.config/bandar/config.json)",
    )
    parser.add_argument("--hidden", action="store_true", help="start in the system tray")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    config_path = (args.config or default_path()).expanduser().resolve()
    logs.configure(config_path)
    register_source_run(PACKAGE.parent)
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(VERSION)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    # argv[0] becomes the X11 WM_CLASS instance; the class comes from the application name.
    qt = QApplication(["bandar"])
    qt.setApplicationDisplayName(APP_NAME)
    qt.setDesktopFileName(APP_ID)
    qt.setWindowIcon(QIcon(str(ICON)))
    qt.setQuitOnLastWindowClosed(False)

    from bandar.app import Application
    from bandar.instance import SingleInstance
    from bandar.ui.window import MainWindow

    instance = SingleInstance(str(config_path))
    if not instance.claim():
        print(f"{APP_NAME} is already running; its window was brought to the front.")
        return 0
    application = Application(config_path)
    window = MainWindow(application, hidden=args.hidden)
    instance.activated.connect(window.bring_to_front)
    application.boot()

    # Ctrl+C or a service manager's SIGTERM stops every forward before exiting.
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, lambda *_: QTimer.singleShot(0, window.request_quit))
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)  # lets Python run signal handlers
    heartbeat.start(400)
    code = qt.exec()
    instance.release()
    return code
