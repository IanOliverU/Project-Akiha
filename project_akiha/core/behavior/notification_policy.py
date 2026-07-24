"""Notification policy for proactive companion behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum

from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior.activity import ActivitySnapshot, ActivityState


class NotificationUrgency(StrEnum):
    """How important a proactive request is."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class NotificationRequest:
    """A candidate proactive companion action."""

    kind: str
    message: str
    urgency: NotificationUrgency = NotificationUrgency.NORMAL


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    """Policy outcome for a proactive companion action."""

    allowed: bool
    reason: str


class NotificationPolicy:
    """Decide whether Akiha may surface a proactive action right now."""

    def __init__(self, config: BehaviorConfig) -> None:
        self._config = config

    def update_config(self, config: BehaviorConfig) -> None:
        """Apply runtime behavior settings."""
        self._config = config

    def evaluate(
        self,
        request: NotificationRequest,
        *,
        activity: ActivitySnapshot,
        now: datetime,
        last_notification_at: datetime | None = None,
    ) -> NotificationDecision:
        """Return whether the proactive request is allowed."""
        del request

        if not self._config.enabled:
            return NotificationDecision(False, "behavior_disabled")
        if not self._config.proactive_enabled:
            return NotificationDecision(False, "proactive_disabled")
        if self._in_quiet_hours(now):
            return NotificationDecision(False, "quiet_hours")
        if (
            activity.state == ActivityState.AWAY
            and not self._config.allow_notifications_while_away
        ):
            return NotificationDecision(False, "user_away")
        if last_notification_at is not None:
            elapsed_seconds = (now - last_notification_at).total_seconds()
            if elapsed_seconds < self._config.minimum_seconds_between_notifications:
                return NotificationDecision(False, "cooldown")

        return NotificationDecision(True, "allowed")

    def _in_quiet_hours(self, now: datetime) -> bool:
        if not self._config.quiet_hours_enabled:
            return False

        start = _parse_hh_mm(self._config.quiet_hours_start)
        end = _parse_hh_mm(self._config.quiet_hours_end)
        current = now.time().replace(second=0, microsecond=0)
        if start <= end:
            return start <= current < end
        return current >= start or current < end


def _parse_hh_mm(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))
