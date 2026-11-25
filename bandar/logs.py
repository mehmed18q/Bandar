"""Rotating application log beside the configuration, plus crash traces."""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

_state = {"directory": None, "fault": None}


def configure(config_path: Path) -> Path | None:
    """Log to ``<config dir>/logs/bandar.log``; returns the directory (or None)."""
    if _state["directory"]:
        return _state["directory"]
    directory = Path(config_path).parent / "logs"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            directory / "bandar.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger("bandar")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        _state["fault"] = (directory / "crash.log").open("a", encoding="utf-8")
        faulthandler.enable(file=_state["fault"], all_threads=True)
    except OSError:
        pass
    previous = sys.excepthook

    def unhandled(kind, value, trace):
        root.critical("Unhandled exception", exc_info=(kind, value, trace))
        previous(kind, value, trace)

    def unhandled_thread(args):
        root.critical(
            "Unhandled thread exception",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = unhandled
    threading.excepthook = unhandled_thread
    _state["directory"] = directory
    return directory


def directory() -> Path | None:
    return _state["directory"]
