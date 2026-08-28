"""User-scoped single-instance ownership and activation handoff."""

from __future__ import annotations

import hashlib
import os
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QIODevice, QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_ACTIVATE_COMMAND = b"activate\n"
_ACKNOWLEDGEMENT = b"accepted\n"
_MAX_COMMAND_BYTES = 64
_WRITE_FLUSH_TIMEOUT_MS = 50


class SingleInstanceError(RuntimeError):
    """Raised when instance ownership cannot be established safely."""


class SingleInstanceRole(StrEnum):
    """Result of attempting to claim the application runtime."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class _ProbeResult(StrEnum):
    NOTIFIED = "notified"
    STALE_OR_MISSING = "stale_or_missing"
    UNAVAILABLE = "unavailable"


def build_single_instance_name(data_dir: Path) -> str:
    """Return a stable IPC name without exposing the local data path."""
    normalized = os.path.normcase(str(data_dir.resolve(strict=False)))
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]
    return f"project-akiha-{digest}"


class SingleInstanceCoordinator(QObject):
    """Own one local IPC endpoint and receive bounded activation requests."""

    activation_requested = Signal()

    def __init__(
        self,
        server_name: str,
        parent: QObject | None = None,
        *,
        connection_timeout_ms: int = 750,
    ) -> None:
        super().__init__(parent)
        normalized_name = server_name.strip()
        if not normalized_name:
            raise ValueError("The single-instance server name cannot be empty.")
        if not 50 <= connection_timeout_ms <= 5_000:
            raise ValueError("The connection timeout must be between 50 and 5000 ms.")
        self._server_name = normalized_name
        self._connection_timeout_ms = connection_timeout_ms
        self._server: QLocalServer | None = None
        self._connection_buffers: dict[QLocalSocket, bytearray] = {}

    @property
    def is_primary(self) -> bool:
        """Return whether this coordinator owns the local server."""
        return self._server is not None and self._server.isListening()

    def start(self) -> SingleInstanceRole:
        """Claim primary ownership or notify the existing primary instance."""
        if self.is_primary:
            return SingleInstanceRole.PRIMARY

        probe = self._notify_existing_instance()
        if probe == _ProbeResult.NOTIFIED:
            return SingleInstanceRole.SECONDARY
        if probe == _ProbeResult.UNAVAILABLE:
            raise SingleInstanceError(
                "Akiha could not verify whether another instance is running."
            )

        QLocalServer.removeServer(self._server_name)
        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if server.listen(self._server_name):
            server.newConnection.connect(self._accept_connections)
            self._server = server
            return SingleInstanceRole.PRIMARY

        server.deleteLater()
        retry = self._notify_existing_instance()
        if retry == _ProbeResult.NOTIFIED:
            return SingleInstanceRole.SECONDARY
        raise SingleInstanceError(
            "Akiha could not claim its single-instance runtime endpoint."
        )

    def close(self) -> None:
        """Release primary ownership and discard pending local connections."""
        for connection in tuple(self._connection_buffers):
            connection.abort()
            connection.deleteLater()
        self._connection_buffers.clear()
        server = self._server
        self._server = None
        if server is None:
            return
        server.close()
        QLocalServer.removeServer(self._server_name)
        server.deleteLater()

    def _notify_existing_instance(self) -> _ProbeResult:
        socket = QLocalSocket()
        socket.connectToServer(
            self._server_name,
            QIODevice.OpenModeFlag.ReadWrite,
        )
        if socket.waitForConnected(self._connection_timeout_ms):
            socket.write(_ACTIVATE_COMMAND)
            socket.flush()
            socket.waitForBytesWritten(_WRITE_FLUSH_TIMEOUT_MS)
            if socket.waitForReadyRead(self._connection_timeout_ms):
                socket.read(_MAX_COMMAND_BYTES)
            socket.disconnectFromServer()
            return _ProbeResult.NOTIFIED

        error = socket.error()
        socket.abort()
        if error in {
            QLocalSocket.LocalSocketError.ServerNotFoundError,
            QLocalSocket.LocalSocketError.ConnectionRefusedError,
        }:
            return _ProbeResult.STALE_OR_MISSING
        return _ProbeResult.UNAVAILABLE

    def _accept_connections(self) -> None:
        server = self._server
        if server is None:
            return
        while server.hasPendingConnections():
            connection = server.nextPendingConnection()
            if connection is None:
                continue
            self._connection_buffers[connection] = bytearray()
            connection.readyRead.connect(
                lambda connection=connection: self._read_command(connection)
            )
            connection.disconnected.connect(
                lambda connection=connection: self._finish_connection(connection)
            )
            self._read_command(connection)

    def _read_command(self, connection: QLocalSocket) -> None:
        buffer = self._connection_buffers.get(connection)
        if buffer is None:
            return
        available = min(connection.bytesAvailable(), _MAX_COMMAND_BYTES - len(buffer))
        if available > 0:
            buffer.extend(bytes(connection.read(available)))
        if len(buffer) >= _MAX_COMMAND_BYTES or b"\n" in buffer:
            command = bytes(buffer).split(b"\n", 1)[0]
            self._connection_buffers.pop(connection, None)
            if command == _ACTIVATE_COMMAND.rstrip():
                self.activation_requested.emit()
                connection.write(_ACKNOWLEDGEMENT)
                connection.flush()
                connection.waitForBytesWritten(_WRITE_FLUSH_TIMEOUT_MS)
            connection.disconnectFromServer()

    def _discard_connection(self, connection: QLocalSocket) -> None:
        self._connection_buffers.pop(connection, None)
        connection.deleteLater()

    def _finish_connection(self, connection: QLocalSocket) -> None:
        self._read_command(connection)
        self._discard_connection(connection)
