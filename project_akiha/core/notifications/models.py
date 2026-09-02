"""Bounded records used by the sanitized Notification Center."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from project_akiha.core.integrations import (
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)


class NotificationInboxStatus(StrEnum):
    """User-facing delivery state retained by the inbox."""

    PENDING = "pending"
    DELIVERED = "delivered"
    SUPPRESSED = "suppressed"
    SILENT = "silent"
    EXPIRED = "expired"


class NotificationChannelMode(StrEnum):
    """Closed channel modes supported by external notification policy."""

    VISUAL_CHAT_VOICE = "visual_chat_voice"
    VISUAL_CHAT = "visual_chat"
    VISUAL_ONLY = "visual_only"
    CHAT_ONLY = "chat_only"
    VOICE_ONLY = "voice_only"
    SILENT = "silent"


@dataclass(frozen=True, slots=True)
class NotificationChannelDecision:
    """Explicit channels allowed for one sanitized event."""

    tray: bool
    chat: bool
    voice: bool

    @property
    def silent(self) -> bool:
        """Return whether no user-facing channel is allowed."""
        return not (self.tray or self.chat or self.voice)


@dataclass(frozen=True, slots=True)
class SanitizedNotification:
    """Rendered notification safe for bounded local persistence."""

    service: ExternalService
    event_kind: ExternalEventKind
    priority: ExternalEventPriority
    display_text: str
    occurred_at: datetime
    created_at: datetime
    status: NotificationInboxStatus = NotificationInboxStatus.PENDING
    aggregate_count: int = 1

    def __post_init__(self) -> None:
        text = self.display_text.strip()
        if not text or len(text) > 320:
            raise ValueError(
                "Notification display text must contain 1 to 320 characters."
            )
        if self.occurred_at.tzinfo is None or self.created_at.tzinfo is None:
            raise ValueError("Notification timestamps must be timezone-aware.")
        if not 1 <= self.aggregate_count <= 100:
            raise ValueError("Notification aggregate count must be between 1 and 100.")
        object.__setattr__(self, "display_text", text)


@dataclass(frozen=True, slots=True)
class NotificationInboxRecord(SanitizedNotification):
    """One durable Notification Center row."""

    id: int = 0
    read_at: datetime | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.id < 1:
            raise ValueError("Notification record id must be positive.")
        if self.read_at is not None and self.read_at.tzinfo is None:
            raise ValueError("Notification read timestamp must be timezone-aware.")


class NotificationInboxRepository(Protocol):
    """Persistence boundary for sanitized Notification Center records."""

    def add(self, notification: SanitizedNotification) -> int:
        """Persist a sanitized record and return its identifier."""

    def list_recent(
        self, *, limit: int = 200, unread_only: bool = False
    ) -> tuple[NotificationInboxRecord, ...]:
        """Return bounded newest-first records."""

    def update_status(self, record_id: int, status: NotificationInboxStatus) -> None:
        """Update one delivery state."""

    def mark_read(self, record_ids: tuple[int, ...], *, read_at: datetime) -> int:
        """Mark selected records read and return the changed count."""

    def mark_all_read(self, *, read_at: datetime) -> int:
        """Mark every unread record read."""

    def clear(self) -> int:
        """Delete all notification records."""

    def prune(self, *, maximum_records: int, older_than: datetime) -> int:
        """Apply age and count retention bounds."""
