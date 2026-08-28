"""Qt worker for bounded Gmail desktop authorization."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.config import GmailIntegrationConfig
from project_akiha.integrations.gmail.auth import GmailOAuthError, GmailToken
from project_akiha.integrations.gmail.oauth_flow import authorize_gmail

AuthorizationService = Callable[
    [GmailIntegrationConfig, Callable[[str], None], threading.Event, str],
    GmailToken,
]


class GmailAuthorizationThread(QThread):
    """Wait for Google's loopback callback without blocking Settings."""

    authorization_url_ready = Signal(str)
    authorization_ready = Signal(object)
    authorization_failed = Signal(str)

    def __init__(
        self,
        config: GmailIntegrationConfig,
        client_secret: str,
        parent: QObject | None = None,
        *,
        service: AuthorizationService = authorize_gmail,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._client_secret = client_secret
        self._service = service
        self._cancel_event = threading.Event()

    def run(self) -> None:
        """Complete authorization and expose only sanitized failures."""
        try:
            token = self._service(
                self._config,
                self.authorization_url_ready.emit,
                self._cancel_event,
                self._client_secret,
            )
        except GmailOAuthError as error:
            self.authorization_failed.emit(str(error))
            return
        except Exception:
            self.authorization_failed.emit("Gmail authorization failed.")
            return
        self.authorization_ready.emit(token)

    def cancel(self) -> None:
        """Ask the bounded callback listener to stop."""
        self._cancel_event.set()
