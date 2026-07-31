"""Qt worker for the bounded Spotify browser authorization flow."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.config import SpotifyConfig
from project_akiha.services.spotify_auth import SpotifyOAuthError, SpotifyToken
from project_akiha.services.spotify_oauth_flow import authorize_spotify

AuthorizationService = Callable[
    [SpotifyConfig, Callable[[str], None], threading.Event],
    SpotifyToken,
]


class SpotifyAuthorizationThread(QThread):
    """Wait for Spotify's loopback callback without blocking the Settings UI."""

    authorization_url_ready = Signal(str)
    authorization_ready = Signal(object)
    authorization_failed = Signal(str)

    def __init__(
        self,
        config: SpotifyConfig,
        parent: QObject | None = None,
        *,
        service: AuthorizationService = authorize_spotify,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._service = service
        self._cancel_event = threading.Event()

    def run(self) -> None:
        """Complete authorization and return only privacy-safe failures."""
        try:
            token = self._service(
                self._config,
                self.authorization_url_ready.emit,
                self._cancel_event,
            )
        except SpotifyOAuthError as error:
            self.authorization_failed.emit(str(error))
            return
        except Exception:
            self.authorization_failed.emit("Spotify authorization failed.")
            return
        self.authorization_ready.emit(token)

    def cancel(self) -> None:
        """Ask the bounded callback listener to stop."""
        self._cancel_event.set()
