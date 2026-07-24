"""Application-level proactive suggestion wiring."""

from __future__ import annotations

from datetime import datetime

from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    ProactiveSuggestion,
    ProactiveSuggestionEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ProactiveController:
    """Evaluate activity state changes and publish allowed suggestions."""

    def __init__(
        self,
        event_bus: EventBus,
        suggestion_engine: ProactiveSuggestionEngine,
    ) -> None:
        self._event_bus = event_bus
        self._suggestion_engine = suggestion_engine
        event_bus.subscribe(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            self._handle_activity_state_changed,
        )

    def evaluate_snapshot(
        self,
        snapshot: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Evaluate an activity snapshot and publish any allowed suggestion."""
        suggestion = self._suggestion_engine.evaluate_activity(snapshot, now)
        if suggestion is not None:
            self._publish_suggestion(suggestion)
        return suggestion

    def _handle_activity_state_changed(self, event: Event) -> None:
        snapshot = _snapshot_from_payload(event.payload)
        if snapshot is None:
            return
        self.evaluate_snapshot(snapshot)

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


def _snapshot_from_payload(payload: dict[str, object]) -> ActivitySnapshot | None:
    state_value = payload.get("state")
    idle_seconds = payload.get("idle_seconds")
    last_activity_at = payload.get("last_activity_at")
    source = payload.get("source")

    if not isinstance(state_value, str):
        return None
    if not isinstance(idle_seconds, int):
        return None
    if not isinstance(last_activity_at, str):
        return None
    if not isinstance(source, str):
        return None

    try:
        state = ActivityState(state_value)
        parsed_last_activity_at = datetime.fromisoformat(last_activity_at)
    except ValueError:
        return None

    return ActivitySnapshot(
        state=state,
        idle_seconds=idle_seconds,
        last_activity_at=parsed_last_activity_at,
        source=source,
    )
