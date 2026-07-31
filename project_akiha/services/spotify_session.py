"""Thread-safe authenticated Spotify session with memory-only access tokens."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from project_akiha.config import SpotifyConfig
from project_akiha.services.credential_store import NamedSecretStore
from project_akiha.services.spotify_auth import (
    SpotifyOAuthError,
    SpotifyToken,
    refresh_spotify_access_token,
)

SpotifyTokenRefresher = Callable[[SpotifyConfig, str], SpotifyToken]


class SpotifySession:
    """Provide valid access tokens without persisting short-lived credentials."""

    def __init__(
        self,
        config: SpotifyConfig,
        secret_store: NamedSecretStore,
        *,
        token_refresher: SpotifyTokenRefresher = refresh_spotify_access_token,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._secret_store = secret_store
        self._token_refresher = token_refresher
        self._now = now
        self._access_token: SpotifyToken | None = None
        self._lock = threading.RLock()

    @property
    def is_connected(self) -> bool:
        """Return whether an encrypted refresh token is available."""
        return (
            self._secret_store.get_named_secret("spotify", "refresh_token") is not None
        )

    def apply_config(self, config: SpotifyConfig) -> None:
        """Apply public settings and discard access tokens when identity changes."""
        with self._lock:
            if config.client_id != self._config.client_id or not config.enabled:
                self._access_token = None
            self._config = config

    def get_access_token(self) -> str:
        """Return a cached token or refresh it from the DPAPI-protected secret."""
        with self._lock:
            if not self._config.enabled:
                raise SpotifyOAuthError("Spotify integration is disabled.")
            cached = self._access_token
            if cached is not None and cached.expires_at > self._now() + 30.0:
                return cached.access_token

            refresh_token = self._secret_store.get_named_secret(
                "spotify",
                "refresh_token",
            )
            if refresh_token is None:
                raise SpotifyOAuthError(
                    "Spotify is not connected. Connect it from Settings first."
                )
            refreshed = self._token_refresher(self._config, refresh_token)
            if refreshed.refresh_token != refresh_token:
                self._secret_store.set_named_secret(
                    "spotify",
                    "refresh_token",
                    refreshed.refresh_token,
                )
            self._access_token = refreshed
            return refreshed.access_token

    def clear_access_token(self) -> None:
        """Discard the in-memory token after an authorization failure."""
        with self._lock:
            self._access_token = None

    def disconnect(self) -> None:
        """Remove Spotify authorization without changing public settings."""
        with self._lock:
            self._access_token = None
            self._secret_store.delete_named_secret("spotify", "refresh_token")
