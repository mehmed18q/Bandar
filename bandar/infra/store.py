"""The configuration repository: one JSON file, written asynchronously and watched.

Writes are coalesced: while one write runs, only the newest pending snapshot is
kept. Edits made to the file by hand are detected and reloaded; an invalid
hand edit pauses saving instead of being overwritten.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from bandar.core import config as cfg

log = logging.getLogger(__name__)
RELOAD_DEBOUNCE_MS = 350


class ConfigStore(QObject):
    saveFailed = Signal(str)
    externalChange = Signal(object)  # a normalized config edited outside Bandar
    externalInvalid = Signal(str)  # parse error detail; saving is paused

    def __init__(self, path: Path, tasks, parent=None):
        super().__init__(parent)
        self.path = Path(path)
        self._tasks = tasks
        self._lock = threading.Lock()
        self._pending = None
        self._writing = False
        self._known_text = None  # the file content Bandar last read or wrote
        self.read_only = False
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._schedule_check)
        self._watcher.directoryChanged.connect(self._schedule_check)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(RELOAD_DEBOUNCE_MS)
        self._debounce.timeout.connect(self._check_external)

    # ------------------------------------------------------------ reading

    def load(self):
        config, notice = cfg.load(self.path)
        self.read_only = bool(notice and notice.get("readOnly"))
        try:
            self._known_text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._known_text = None
        self._watch()
        return config, notice

    def _watch(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if str(self.path.parent) not in self._watcher.directories():
            self._watcher.addPath(str(self.path.parent))
        if self.path.exists() and str(self.path) not in self._watcher.files():
            self._watcher.addPath(str(self.path))

    def _schedule_check(self, *_):
        self._debounce.start()

    def _check_external(self):
        with self._lock:
            busy = self._writing
        if busy:
            self._debounce.start()
            return
        self._watch()
        self._tasks.run(self._read_text, callback=self._compare)

    def _read_text(self):
        try:
            return self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def _compare(self, text):
        if isinstance(text, Exception) or text is None:
            return
        with self._lock:
            if text == self._known_text or self._writing:
                return
        try:
            config = cfg.parse(text)
        except cfg.ConfigError as error:
            self.read_only = True
            self.externalInvalid.emit(error.detail)
            return
        with self._lock:
            self._known_text = text
        self.read_only = False
        log.info("Configuration reloaded after an external edit")
        self.externalChange.emit(config)

    # ------------------------------------------------------------ writing

    def save(self, config: dict):
        """Queue ``config`` for writing. Never blocks; ignored while read-only."""
        if self.read_only:
            return
        text = cfg.dumps(config)
        with self._lock:
            if text == self._known_text and self._pending is None:
                return
            self._pending = text
            if self._writing:
                return
            self._writing = True
        self._tasks.run(self._drain, callback=self._drained)

    def _drain(self):
        """Worker thread: write snapshots until none is pending. Returns the last error."""
        error = None
        while True:
            with self._lock:
                text, self._pending = self._pending, None
                if text is None:
                    self._writing = False
                    return error
            try:
                cfg.write_atomic(self.path, text)
            except OSError as failure:
                error = str(failure)
                continue
            with self._lock:
                self._known_text = text
            error = None

    def _drained(self, error):
        if isinstance(error, Exception):
            error = str(error)
            with self._lock:
                self._writing = False
        if error:
            log.error("Saving %s failed: %s", self.path, error)
            self.saveFailed.emit(error)
        self._watch()

    def flush(self, config: dict):
        """Write synchronously; used once on exit, after background work has stopped."""
        if self.read_only:
            return
        text = cfg.dumps(config)
        if text != self._known_text:
            try:
                cfg.write_atomic(self.path, text)
                self._known_text = text
            except OSError as error:
                log.error("Final save failed: %s", error)

    def reset(self):
        """Move an unusable file aside so a fresh one can be written."""
        moved = cfg.backup(self.path) if self.path.exists() else None
        self.read_only = False
        self._known_text = None
        return moved
