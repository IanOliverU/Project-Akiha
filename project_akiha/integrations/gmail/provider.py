"""Bounded metadata-only Gmail polling provider."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from project_akiha.config import GmailIntegrationConfig
from project_akiha.core.integrations import (
    ExternalEvent,
    ExternalEventRepository,
    ExternalService,
)
from project_akiha.integrations.gmail.auth import GmailOAuthError
from project_akiha.integrations.gmail.classification import classify_gmail_metadata
from project_akiha.integrations.gmail.client import (
    GmailApiClient,
    GmailApiError,
    GmailCursorExpired,
    GmailMessageMetadata,
)
from project_akiha.integrations.gmail.session import GmailSession

HealthCallback = Callable[[ExternalService, str, datetime], None]


class GmailIntegrationProvider:
    """Poll Gmail metadata incrementally without retaining message bodies."""

    def __init__(
        self,
        config: GmailIntegrationConfig,
        session: GmailSession,
        client: GmailApiClient,
        repository: ExternalEventRepository,
        *,
        on_health: HealthCallback | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._session = session
        self._client = client
        self._repository = repository
        self._on_health = on_health
        self._logger = logger or logging.getLogger("project_akiha.integrations.gmail")
        self._health_status = "disabled" if not config.enabled else "disconnected"
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_event: Callable[[ExternalEvent], None] | None = None

    @property
    def service(self) -> ExternalService:
        return ExternalService.GMAIL

    @property
    def health_status(self) -> str:
        return self._health_status

    def apply_config(self, config: GmailIntegrationConfig) -> None:
        """Apply settings; lifecycle changes take effect through restart."""
        self._config = config
        self._session.apply_config(config)
        self._client.apply_timeout(config.request_timeout_seconds)
        self._refresh_event.set()

    def start(self, on_event: Callable[[ExternalEvent], None]) -> None:
        """Start one cancellable daemon polling worker."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._on_event = on_event
        self._stop_event.clear()
        self._refresh_event.clear()
        if not self._config.enabled:
            self._set_health("disabled")
            return
        self._thread = threading.Thread(
            target=self._run,
            name="AkihaGmailPolling",
            daemon=True,
        )
        self._thread.start()

    def refresh(self) -> None:
        """Wake the worker for one immediate bounded synchronization."""
        self._refresh_event.set()

    def stop(self) -> None:
        """Cancel polling and reject late callbacks."""
        self._stop_event.set()
        self._refresh_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._thread = None
        self._on_event = None
        self._session.clear()
        self._set_health("stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._poll_safely()
            if self._stop_event.is_set():
                break
            self._refresh_event.wait(self._config.poll_interval_seconds)
            self._refresh_event.clear()

    def _poll_safely(self) -> None:
        self._set_health("connecting")
        try:
            self._poll_once()
        except GmailOAuthError:
            self._set_health("authentication_failure")
        except GmailApiError as error:
            self._set_health(error.code)
        except Exception:
            self._logger.exception("Gmail synchronization failed safely.")
            self._set_health("provider_unavailable")
        else:
            self._set_health("available")

    def _poll_once(self) -> None:
        access_token = self._session.access_token()
        profile = self._client.get_profile(access_token)
        cursor = self._repository.load_sync_cursor(
            ExternalService.GMAIL,
            profile.account_key,
        )
        synchronized_at = datetime.now(tz=UTC)
        if cursor is None:
            self._repository.save_sync_cursor(
                ExternalService.GMAIL,
                profile.account_key,
                profile.history_id,
                synchronized_at=synchronized_at,
            )
            return

        final_cursor = cursor
        page_token: str | None = None
        try:
            while True:
                page = self._client.list_history(
                    access_token,
                    cursor,
                    page_token=page_token,
                )
                for message_id in page.message_ids:
                    self._emit_metadata(
                        self._client.get_message_metadata(access_token, message_id)
                    )
                final_cursor = page.history_id
                page_token = page.next_page_token
                if page_token is None:
                    break
        except GmailCursorExpired:
            self._repository.save_sync_cursor(
                ExternalService.GMAIL,
                profile.account_key,
                profile.history_id,
                synchronized_at=synchronized_at,
            )
            self._set_health("cursor_rebased")
            return

        self._repository.save_sync_cursor(
            ExternalService.GMAIL,
            profile.account_key,
            final_cursor,
            synchronized_at=synchronized_at,
        )

    def _emit_metadata(self, metadata: GmailMessageMetadata) -> None:
        callback = self._on_event
        if callback is None or self._stop_event.is_set():
            return
        classification = classify_gmail_metadata(metadata)
        callback(
            ExternalEvent(
                service=ExternalService.GMAIL,
                external_id=metadata.message_id,
                kind=classification.kind,
                occurred_at=datetime.fromtimestamp(
                    metadata.timestamp_ms / 1000,
                    tz=UTC,
                ),
                sender_display=metadata.sender,
                subject=metadata.subject,
                context_label="Inbox",
                classification=classification.classification,
                priority=classification.priority,
            )
        )

    def _set_health(self, status: str) -> None:
        self._health_status = status
        callback = self._on_health
        if callback is not None:
            callback(ExternalService.GMAIL, status, datetime.now(tz=UTC))
