"""Run blocking work on a thread pool and deliver results on the Qt thread."""

from __future__ import annotations

import contextlib
import logging
from concurrent.futures import Future, ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)


class TaskRunner(QObject):
    """The single place where the application leaves the UI thread.

    Callbacks always run on the thread that owns this object, so they may touch
    Qt objects and application state freely. A failed task passes its exception
    to the callback instead of a result.
    """

    _finished = Signal(object, object)

    def __init__(self, workers: int = 3, parent=None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="bandar")
        self._closed = False
        self._finished.connect(self._deliver)

    def run(self, function, *args, callback=None) -> Future | None:
        if self._closed:
            return None
        future = self._pool.submit(function, *args)
        future.add_done_callback(lambda done: self._emit(callback, done))
        return future

    def _emit(self, callback, future):
        if self._closed:
            return
        with contextlib.suppress(RuntimeError):  # destroyed during shutdown
            self._finished.emit(callback, future)

    def _deliver(self, callback, future: Future):
        if callback is None or future.cancelled():
            return
        error = future.exception()
        if error is not None:
            log.warning("Background task failed: %s", error, exc_info=error)
        try:
            callback(error if error is not None else future.result())
        except Exception:
            log.exception("Task callback failed")

    def shutdown(self, wait: bool = False):
        self._closed = True
        self._pool.shutdown(wait=wait, cancel_futures=True)
