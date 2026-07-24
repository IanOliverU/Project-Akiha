"""Application-level companion mood wiring."""

from __future__ import annotations

from datetime import datetime

from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    MoodEngine,
    MoodSnapshot,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class MoodController:
    """Translate app events into companion mood state changes."""

    _interaction_sources = {
        EventType.CHAT_OPEN_REQUESTED: "chat_open_requested",
        EventType.SETTINGS_OPEN_REQUESTED: "settings_open_requested",
        EventType.PET_DRAG_STARTED: "pet_drag_started",
        EventType.PET_WALK_REQUESTED: "pet_walk_requested",
        EventType.PET_IDLE_REQUESTED: "pet_idle_requested",
        EventType.PET_WAKE_REQUESTED: "pet_wake_requested",
    }

    def __init__(
        self,
        event_bus: EventBus,
        mood_engine: MoodEngine,
    ) -> None:
        self._event_bus = event_bus
        self._mood_engine = mood_engine
        self._last_published = mood_engine.snapshot

        event_bus.subscribe(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            self._handle_activity_state_changed,
        )
        event_bus.subscribe(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            self._handle_suggestion_delivered,
        )
        event_bus.subscribe(EventType.PET_SLEEP_REQUESTED, self._handle_sleep_requested)
        for event_type in self._interaction_sources:
            event_bus.subscribe(event_type, self._handle_interaction)

        self._publish_mood(mood_engine.snapshot)

    @property
    def snapshot(self) -> MoodSnapshot:
        """Return the current mood snapshot."""
        return self._mood_engine.snapshot

    def _handle_activity_state_changed(self, event: Event) -> None:
        snapshot = _activity_from_payload(event.payload)
        if snapshot is None:
            return
        self._publish_if_changed(self._mood_engine.observe_activity(snapshot))

    def _handle_suggestion_delivered(self, event: Event) -> None:
        delivered = event.payload.get("delivered")
        reason = event.payload.get("reason")
        if not isinstance(delivered, bool) or not isinstance(reason, str):
            return
        self._publish_if_changed(
            self._mood_engine.observe_delivery_result(
                delivered=delivered,
                reason=reason,
            )
        )

    def _handle_sleep_requested(self, event: Event) -> None:
        del event
        self._publish_if_changed(self._mood_engine.observe_sleep_requested())

    def _handle_interaction(self, event: Event) -> None:
        source = self._interaction_sources[event.event_type]
        if event.event_type == EventType.PET_WAKE_REQUESTED:
            snapshot = self._mood_engine.observe_wake_requested()
        else:
            snapshot = self._mood_engine.observe_interaction(source)
        self._publish_if_changed(snapshot)

    def _publish_if_changed(self, snapshot: MoodSnapshot) -> None:
        if (
            snapshot.mood == self._last_published.mood
            and snapshot.reason == self._last_published.reason
        ):
            return
        self._publish_mood(snapshot)

    def _publish_mood(self, snapshot: MoodSnapshot) -> None:
        self._last_published = snapshot
        self._event_bus.publish(
            EventType.MOOD_STATE_CHANGED,
            {
                "mood": snapshot.mood.value,
                "reason": snapshot.reason,
                "updated_at": snapshot.updated_at.isoformat(),
            },
        )


def _activity_from_payload(payload: dict[str, object]) -> ActivitySnapshot | None:
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
