"""Bounded history fetch off the GUI thread; no playback or durable output."""

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.actions.clarification import SpotifyHistoryIdentity
from project_akiha.integrations.spotify.client import SpotifyClient
from project_akiha.integrations.spotify.history import fetch_spotify_history
from project_akiha.integrations.spotify.session import SpotifySession


class SpotifyHistoryThread(QThread):
    result_ready = Signal(object)

    def __init__(
        self,
        client: SpotifyClient,
        session: SpotifySession,
        identity: SpotifyHistoryIdentity,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._session = session
        self._identity = identity

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        result = fetch_spotify_history(
            self._client, self._session, self._identity.account_generation
        )
        if not self.isInterruptionRequested():
            self.result_ready.emit(result)

    def cancel(self) -> None:
        self.requestInterruption()
