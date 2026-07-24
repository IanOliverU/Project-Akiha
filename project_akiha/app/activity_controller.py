"""Application-level activity awareness wiring."""

from __future__ import annotations

from datetime import datetime

from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import ActivitySnapshot, ActivityTracker
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ActivityController:
    """Translate app events into user activity state changes."""

    _activity_event_sources = {
        EventType.PET_DRAG_STARTED: "pet_drag_started",
        EventType.PET_DRAGGED: "pet_dragged",
        EventType.PET_DRAG_ENDED: "pet_drag_ended",
        EventType.PET_WALK_REQUESTED: "pet_walk_requested",
        EventType.PET_IDLE_REQUESTED: "pet_idle_requested",
        EventType.PET_SLEEP_REQUESTED: "pet_sleep_requested",
        EventType.PET_WAKE_REQUESTED: "pet_wake_requested",
        EventType.CHAT_OPEN_REQUESTED: "chat_open_requested",
        EventType.SETTINGS_OPEN_REQUESTED: "settings_open_requested",
    }

    def __init__(
        self,
        event_bus: EventBus,
        config: BehaviorConfig,
        initial_time: datetime | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        self._tracker = ActivityTracker(
            idle_after_seconds=config.idle_after_seconds,
            away_after_seconds=config.away_after_seconds,
            initial_time=initial_time,
        )
        self._last_snapshot = self._tracker.snapshot(initial_time)

        for event_type in self._activity_event_sources:
            event_bus.subscribe(event_type, self._handle_activity_event)

        self._publish_state_changed(self._last_snapshot)

    @property
    def snapshot(self) -> ActivitySnapshot:
        """Return the last evaluated activity snapshot."""
        return self._last_snapshot

    def apply_config(self, config: BehaviorConfig) -> None:
        """Apply runtime behavior thresholds."""
        self._config = config
        self._tracker.update_thresholds(
            idle_after_seconds=config.idle_after_seconds,
            away_after_seconds=config.away_after_seconds,
        )
        self.tick()

    def record_activity(
        self,
        source: str,
        occurred_at: datetime | None = None,
    ) -> ActivitySnapshot:
        """Record activity from code paths that do not publish app events."""
        snapshot = self._tracker.record_activity(source, occurred_at)
        self._publish_observed(snapshot)
        self._set_snapshot(snapshot)
        return snapshot

    def tick(self, now: datetime | None = None) -> ActivitySnapshot:
        """Evaluate idle/away transitions and publish state changes."""
        snapshot = self._tracker.snapshot(now)
        self._set_snapshot(snapshot)
        return snapshot

    def _handle_activity_event(self, event: Event) -> None:
        if not self._config.enabled:
            return

        source = self._activity_event_sources[event.event_type]
        self.record_activity(source)

    def _set_snapshot(self, snapshot: ActivitySnapshot) -> None:
        previous_state = self._last_snapshot.state
        self._last_snapshot = snapshot
        if snapshot.state != previous_state:
            self._publish_state_changed(snapshot)

    def _publish_observed(self, snapshot: ActivitySnapshot) -> None:
        self._event_bus.publish(
            EventType.USER_ACTIVITY_OBSERVED,
            _snapshot_payload(snapshot),
        )

    def _publish_state_changed(self, snapshot: ActivitySnapshot) -> None:
        self._event_bus.publish(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            _snapshot_payload(snapshot),
        )


def _snapshot_payload(snapshot: ActivitySnapshot) -> dict[str, object]:
    return {
        "state": snapshot.state.value,
        "idle_seconds": snapshot.idle_seconds,
        "last_activity_at": snapshot.last_activity_at.isoformat(),
        "source": snapshot.source,
    }
