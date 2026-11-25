"""One Bandar per user and configuration: a second launch raises the first window."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from bandar import APP_ID


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        digest = sha256(f"{Path.home()}|{key}".encode()).hexdigest()[:16]
        self.name = f"{APP_ID}-{digest}"
        temp = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
        self.lock = QLockFile(str(Path(temp) / f"{self.name}.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self._accept)

    def claim(self) -> bool:
        """True when this process is the owner; otherwise the owner was asked to show itself."""
        if self.lock.tryLock(150):
            QLocalServer.removeServer(self.name)
            self.server.listen(self.name)
            return True
        client = QLocalSocket()
        client.connectToServer(self.name)
        if client.waitForConnected(1000):
            client.write(b"show\n")
            client.waitForBytesWritten(1000)
            client.disconnectFromServer()
            return False
        # The lock holder does not answer: it is stuck or exiting. Run anyway.
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.readyRead.connect(lambda c=client: self._read(c))
            client.disconnected.connect(client.deleteLater)

    def _read(self, client):
        if bytes(client.readAll().data()).startswith(b"show"):
            self.activated.emit()

    def release(self):
        self.server.close()
        self.lock.unlock()
