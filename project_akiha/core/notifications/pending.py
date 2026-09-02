"""Bounded in-memory queue for deferred external notifications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from project_akiha.core.integrations import ExternalEvent
from project_akiha.core.notifications.models import NotificationChannelDecision


@dataclass(frozen=True, slots=True)
class PendingNotification:
    """One validated event waiting for the existing presentation path."""

    event: ExternalEvent
    display_text: str
    speech_text: str
    channels: NotificationChannelDecision
    enqueued_at: datetime
    eligible_at: datetime


@dataclass(frozen=True, slots=True)
class PendingEnqueueResult:
    """Outcome of one bounded queue insertion."""

    accepted: bool
    evicted: PendingNotification | None = None


@dataclass(frozen=True, slots=True)
class PendingNotificationBatch:
    """Compatible pending notices collapsed into one delivery."""

    notifications: tuple[PendingNotification, ...]

    @property
    def count(self) -> int:
        return len(self.notifications)


class PendingNotificationQueue:
    """Keep deferred notices bounded and aggregate only compatible events."""

    def __init__(self, *, maximum_size: int = 100) -> None:
        if maximum_size < 1:
            raise ValueError("maximum_size must be positive.")
        self._maximum_size = maximum_size
        self._items: list[PendingNotification] = []

    @property
    def size(self) -> int:
        return len(self._items)

    def enqueue(self, notification: PendingNotification) -> PendingEnqueueResult:
        """Queue one notice, dropping low priority first when full."""
        if len(self._items) >= self._maximum_size:
            ranks = {
                "silent": 0,
                "low": 1,
                "normal": 2,
                "important": 3,
                "critical": 4,
            }
            incoming_rank = ranks[notification.event.priority.value]
            lowest_rank = min(ranks[item.event.priority.value] for item in self._items)
            if lowest_rank > incoming_rank or lowest_rank >= ranks["important"]:
                return PendingEnqueueResult(accepted=False)
            removable = next(
                index
                for index, item in enumerate(self._items)
                if ranks[item.event.priority.value] == lowest_rank
            )
            evicted = self._items.pop(removable)
            self._items.append(notification)
            return PendingEnqueueResult(accepted=True, evicted=evicted)
        self._items.append(notification)
        return PendingEnqueueResult(accepted=True)

    def drain_ready(
        self,
        *,
        now: datetime,
        presentation_busy: bool,
        expiry_seconds: int,
    ) -> tuple[PendingNotificationBatch, ...]:
        """Return ready groups while retaining future or presentation-blocked items."""
        retained: list[PendingNotification] = []
        ready: list[PendingNotification] = []
        for item in self._items:
            if presentation_busy or item.eligible_at > now:
                retained.append(item)
            else:
                ready.append(item)
        self._items = retained

        groups: dict[tuple[str, str, bool, bool, bool], list[PendingNotification]] = {}
        for item in ready:
            key = (
                item.event.service.value,
                item.event.kind.value,
                item.channels.tray,
                item.channels.chat,
                item.channels.voice,
            )
            groups.setdefault(key, []).append(item)
        return tuple(
            PendingNotificationBatch(tuple(group)) for group in groups.values()
        )

    def expire(
        self, *, now: datetime, expiry_seconds: int
    ) -> tuple[PendingNotification, ...]:
        """Remove and return events whose bounded delivery window elapsed."""
        expired: list[PendingNotification] = []
        retained: list[PendingNotification] = []
        for item in self._items:
            if (now - item.event.occurred_at).total_seconds() > expiry_seconds:
                expired.append(item)
            else:
                retained.append(item)
        self._items = retained
        return tuple(expired)

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        return count
