"""Proactive companion suggestion generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from project_akiha.core.behavior.activity import ActivitySnapshot, ActivityState
from project_akiha.core.behavior.notification_policy import (
    NotificationPolicy,
    NotificationRequest,
    NotificationUrgency,
)


@dataclass(frozen=True, slots=True)
class ProactiveSuggestion:
    """A companion suggestion that passed policy checks."""

    kind: str
    message: str
    urgency: NotificationUrgency
    created_at: datetime
    activity_state: ActivityState
    idle_seconds: int


class ProactiveSuggestionEngine:
    """Generate conservative proactive suggestions from activity state."""

    _idle_check_in_kind = "idle_check_in"
    _idle_check_in_message = (
        "You've been quiet for a bit. Want to stretch or take a short pause?"
    )

    def __init__(self, notification_policy: NotificationPolicy) -> None:
        self._notification_policy = notification_policy
        self._last_suggestion_at: datetime | None = None

    @property
    def last_suggestion_at(self) -> datetime | None:
        """Return when the last suggestion passed policy checks."""
        return self._last_suggestion_at

    def evaluate_activity(
        self,
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Return an allowed suggestion for the activity snapshot, if any."""
        current_time = now or datetime.now(tz=UTC)
        request = self._request_for_activity(activity)
        if request is None:
            return None

        decision = self._notification_policy.evaluate(
            request,
            activity=activity,
            now=current_time,
            last_notification_at=self._last_suggestion_at,
        )
        if not decision.allowed:
            return None

        self._last_suggestion_at = current_time
        return ProactiveSuggestion(
            kind=request.kind,
            message=request.message,
            urgency=request.urgency,
            created_at=current_time,
            activity_state=activity.state,
            idle_seconds=activity.idle_seconds,
        )

    def _request_for_activity(
        self,
        activity: ActivitySnapshot,
    ) -> NotificationRequest | None:
        if activity.state != ActivityState.IDLE:
            return None

        return NotificationRequest(
            kind=self._idle_check_in_kind,
            message=self._idle_check_in_message,
            urgency=NotificationUrgency.LOW,
        )
