"""Gmail access-token lifecycle backed by the encrypted credential store."""

from __future__ import annotations

import threading
import time

from project_akiha.config import GmailIntegrationConfig
from project_akiha.integrations.gmail.auth import (
    GmailOAuthError,
    GmailToken,
    refresh_gmail_access_token,
)
from project_akiha.services.credential_store import NamedSecretStore

_NAMESPACE = "gmail"
_REFRESH_TOKEN_NAME = "refresh_token"
_CLIENT_SECRET_NAME = "client_secret"
_CLIENT_ID_NAME = "client_id"


class GmailSession:
    """Resolve short-lived access tokens without exposing refresh credentials."""

    def __init__(
        self,
        config: GmailIntegrationConfig,
        credential_store: NamedSecretStore,
    ) -> None:
        self._config = config
        self._credential_store = credential_store
        self._token: GmailToken | None = None
        self._lock = threading.Lock()

    def apply_config(self, config: GmailIntegrationConfig) -> None:
        """Apply public settings and invalidate the access-token cache."""
        with self._lock:
            self._config = config
            self._token = None

    def access_token(self) -> str:
        """Return a valid access token or require reconnection."""
        with self._lock:
            if self._token is not None and self._token.expires_at > time.time() + 30:
                return self._token.access_token
            refresh_token = self._credential_store.get_named_secret(
                _NAMESPACE,
                _REFRESH_TOKEN_NAME,
            )
            if refresh_token is None:
                raise GmailOAuthError("Gmail is not connected.")
            client_secret = self._credential_store.get_named_secret(
                _NAMESPACE,
                _CLIENT_SECRET_NAME,
            )
            saved_client_id = self._credential_store.get_named_secret(
                _NAMESPACE,
                _CLIENT_ID_NAME,
            )
            if client_secret is None or saved_client_id != self._config.client_id:
                raise GmailOAuthError(
                    "The Gmail OAuth client secret is missing or belongs to a "
                    "different Client ID. Reconnect Gmail."
                )
            token = refresh_gmail_access_token(
                self._config,
                refresh_token,
                client_secret=client_secret,
            )
            if token.refresh_token != refresh_token:
                self._credential_store.set_named_secret(
                    _NAMESPACE,
                    _REFRESH_TOKEN_NAME,
                    token.refresh_token,
                )
            self._token = token
            return token.access_token

    def clear(self) -> None:
        """Forget only memory-resident access state."""
        with self._lock:
            self._token = None
