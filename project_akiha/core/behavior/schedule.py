"""Scheduled check-in generation for proactive companion behavior."""

from __future__ import annotations

from datetime import UTC, datetime

from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior.activity import ActivitySnapshot
from project_akiha.core.behavior.notification_policy import (
    NotificationPolicy,
    NotificationRequest,
    NotificationUrgency,
)
from project_akiha.core.behavior.proactive import ProactiveSuggestion


class ScheduledCheckInEngine:
    """Generate policy-gated scheduled check-in suggestions."""

    _kind = "scheduled_check_in"
    _message = "Quick check-in from Akiha. How are you doing?"

    def __init__(
        self,
        notification_policy: NotificationPolicy,
        config: BehaviorConfig,
        initial_time: datetime | None = None,
    ) -> None:
        self._notification_policy = notification_policy
        self._config = config
        self._last_check_in_at = initial_time

    @property
    def last_check_in_at(self) -> datetime | None:
        """Return when the last scheduled check-in was emitted."""
        return self._last_check_in_at

    def update_config(self, config: BehaviorConfig) -> None:
        """Apply runtime scheduling settings."""
        self._config = config

    def tick(
        self,
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Return a scheduled check-in suggestion when due and allowed."""
        current_time = now or datetime.now(tz=UTC)
        if not self._config.enabled or not self._config.scheduled_check_ins_enabled:
            self._last_check_in_at = current_time
            return None

        if self._last_check_in_at is None:
            self._last_check_in_at = current_time
            return None

        elapsed_seconds = (current_time - self._last_check_in_at).total_seconds()
        if elapsed_seconds < self._config.scheduled_check_in_interval_seconds:
            return None

        request = NotificationRequest(
            kind=self._kind,
            message=self._message,
            urgency=NotificationUrgency.LOW,
        )
        decision = self._notification_policy.evaluate(
            request,
            activity=activity,
            now=current_time,
            last_notification_at=self._last_check_in_at,
        )
        if not decision.allowed:
            return None

        self._last_check_in_at = current_time
        return ProactiveSuggestion(
            kind=request.kind,
            message=request.message,
            urgency=request.urgency,
            created_at=current_time,
            activity_state=activity.state,
            idle_seconds=activity.idle_seconds,
        )
