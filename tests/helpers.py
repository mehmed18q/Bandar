"""Shared test fixtures: a Qt application, an event-loop waiter and the fake kubectl."""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FAKE_KUBECTL = str(ROOT / "tests" / "fake_kubectl.py")

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

from bandar.core import config as cfg  # noqa: E402


def qt():
    return QCoreApplication.instance() or QCoreApplication([])


def flush_deletes():
    """Run pending deleteLater() calls, which processEvents() alone leaves queued."""
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def wait_until(predicate, timeout=8.0):
    """Run the event loop until ``predicate()`` is true; returns the last value."""
    app = qt()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        flush_deletes()
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


def settings(**overrides):
    values = dict(cfg.DEFAULT_SETTINGS, kubectl=FAKE_KUBECTL, retryMaxDelay=2)
    values.update(overrides)
    return values


def service(**overrides):
    values = {
        "id": "s_test",
        "name": "svc",
        "group": "",
        "context": "main",
        "namespace": "default",
        "kind": "service",
        "target": "ok-db",
        "localPort": 25555,
        "remotePort": 5432,
        "address": "127.0.0.1",
        "extraArgs": [],
        "autoStart": False,
        "note": "",
    }
    values.update(overrides)
    return values
