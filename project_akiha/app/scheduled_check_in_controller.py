"""Application-level scheduled check-in wiring."""

from __future__ import annotations

from datetime import datetime

from project_akiha.core.behavior import (
    ActivitySnapshot,
    ProactiveSuggestion,
    ScheduledCheckInEngine,
)
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType


class ScheduledCheckInController:
    """Publish due scheduled check-ins as proactive suggestions."""

    def __init__(
        self,
        event_bus: EventBus,
        check_in_engine: ScheduledCheckInEngine,
    ) -> None:
        self._event_bus = event_bus
        self._check_in_engine = check_in_engine

    def tick(
        self,
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Evaluate scheduled check-ins and publish any due suggestion."""
        suggestion = self._check_in_engine.tick(activity, now)
        if suggestion is not None:
            self._publish_suggestion(suggestion)
        return suggestion

    def _publish_suggestion(self, suggestion: ProactiveSuggestion) -> None:
        self._event_bus.publish(
            EventType.PROACTIVE_SUGGESTION_READY,
            {
                "kind": suggestion.kind,
                "message": suggestion.message,
                "urgency": suggestion.urgency.value,
                "created_at": suggestion.created_at.isoformat(),
                "activity_state": suggestion.activity_state.value,
                "idle_seconds": suggestion.idle_seconds,
            },
        )
