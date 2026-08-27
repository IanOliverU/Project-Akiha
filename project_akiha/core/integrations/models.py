"""Typed external communication events and provider boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ExternalService(StrEnum):
    """Optional external services supported by Phase 11."""

    GMAIL = "gmail"
    DISCORD = "discord"


class ExternalEventKind(StrEnum):
    """Closed event vocabulary accepted by the application boundary."""

    GMAIL_NEW_MESSAGE = "gmail.new_message"
    GMAIL_IMPORTANT_MESSAGE = "gmail.important_message"
    GMAIL_WORK_CANDIDATE = "gmail.work_candidate"
    GMAIL_RECRUITER_CANDIDATE = "gmail.recruiter_candidate"
    GMAIL_INTERVIEW_CANDIDATE = "gmail.interview_candidate"
    GMAIL_PERSONAL_CANDIDATE = "gmail.personal_candidate"
    GMAIL_NEWSLETTER_CANDIDATE = "gmail.newsletter_candidate"
    GMAIL_PROMOTIONAL_CANDIDATE = "gmail.promotional_candidate"
    DISCORD_BOT_DIRECT_MESSAGE = "discord.bot_direct_message"
    DISCORD_MENTION = "discord.mention"
    DISCORD_AUTHORIZED_CHANNEL_MESSAGE = "discord.authorized_channel_message"
    DISCORD_RELATIONSHIP_CHANGED = "discord.relationship_changed"
    DISCORD_FRIEND_REQUEST_CANDIDATE = "discord.friend_request_candidate"
    DISCORD_FRIEND_DIRECT_MESSAGE = "discord.friend_direct_message"
    DISCORD_UNKNOWN_DIRECT_MESSAGE = "discord.unknown_direct_message"


class ExternalClassification(StrEnum):
    """Best-effort local classification attached to an external event."""

    GENERAL = "general"
    IMPORTANT = "important"
    WORK = "work"
    RECRUITER = "recruiter"
    INTERVIEW = "interview"
    PERSONAL = "personal"
    NEWSLETTER = "newsletter"
    PROMOTIONAL = "promotional"
    UNKNOWN = "unknown"


class ExternalEventPriority(StrEnum):
    """Integration priority before mapping into existing delivery urgency."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    NORMAL = "normal"
    LOW = "low"
    SILENT = "silent"


class ExternalNotificationStatus(StrEnum):
    """Minimal receipt state retained for deduplication and diagnostics."""

    RECEIVED = "received"
    QUEUED = "queued"
    DELIVERED = "delivered"
    SUPPRESSED = "suppressed"
    SILENT = "silent"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ExternalEvent:
    """One bounded provider event before application notification policy."""

    service: ExternalService
    external_id: str
    kind: ExternalEventKind
    occurred_at: datetime
    sender_display: str | None = None
    subject: str | None = None
    context_label: str | None = None
    classification: ExternalClassification = ExternalClassification.UNKNOWN
    priority: ExternalEventPriority = ExternalEventPriority.NORMAL


class ExternalIntegrationProvider(Protocol):
    """Lifecycle contract for optional read-only communication providers."""

    @property
    def service(self) -> ExternalService:
        """Return the service owned by this provider."""

    @property
    def health_status(self) -> str:
        """Return one privacy-safe provider health code."""

    def start(self, on_event: Callable[[ExternalEvent], None]) -> None:
        """Begin optional background monitoring."""

    def refresh(self) -> None:
        """Request one bounded synchronization pass."""

    def stop(self) -> None:
        """Cancel monitoring and reject late callbacks."""


class ExternalEventRepository(Protocol):
    """Minimal persistence needed for event dedupe and sync recovery."""

    def claim_event(self, event: ExternalEvent, *, received_at: datetime) -> bool:
        """Atomically claim an event, returning false for a duplicate."""

    def set_notification_status(
        self,
        event: ExternalEvent,
        status: ExternalNotificationStatus,
        *,
        notified_at: datetime | None = None,
    ) -> None:
        """Update only the receipt status for a claimed event."""

    def load_sync_cursor(
        self, service: ExternalService, account_key: str
    ) -> str | None:
        """Load the last committed provider cursor for a local account key."""

    def save_sync_cursor(
        self,
        service: ExternalService,
        account_key: str,
        cursor: str,
        *,
        synchronized_at: datetime,
    ) -> None:
        """Atomically store one bounded provider cursor."""
