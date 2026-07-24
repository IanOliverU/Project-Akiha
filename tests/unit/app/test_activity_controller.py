"""Tests for app-level activity awareness wiring."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.app.activity_controller import ActivityController
from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import ActivityState
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ActivityControllerTest(unittest.TestCase):
    """Verify app events are converted into activity state updates."""

    def test_publishes_initial_activity_state(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.USER_ACTIVITY_STATE_CHANGED, received.append)

        ActivityController(bus, BehaviorConfig(), initial_time=_start())

        self.assertEqual(received[-1].payload["state"], "active")
        self.assertEqual(received[-1].payload["source"], "startup")

    def test_chat_open_event_publishes_activity_observation(self) -> None:
        bus = EventBus()
        observed: list[Event] = []
        bus.subscribe(EventType.USER_ACTIVITY_OBSERVED, observed.append)
        ActivityController(bus, BehaviorConfig(), initial_time=_start())

        bus.publish(EventType.CHAT_OPEN_REQUESTED)

        self.assertEqual(observed[-1].payload["state"], "active")
        self.assertEqual(observed[-1].payload["source"], "chat_open_requested")

    def test_tick_publishes_state_change_when_user_becomes_idle(self) -> None:
        bus = EventBus()
        state_changes: list[Event] = []
        bus.subscribe(EventType.USER_ACTIVITY_STATE_CHANGED, state_changes.append)
        controller = ActivityController(
            bus,
            BehaviorConfig(idle_after_seconds=300, away_after_seconds=900),
            initial_time=_start(),
        )

        controller.tick(_start() + timedelta(seconds=300))

        self.assertEqual(state_changes[-1].payload["state"], "idle")

    def test_disabled_behavior_ignores_activity_events(self) -> None:
        bus = EventBus()
        observed: list[Event] = []
        bus.subscribe(EventType.USER_ACTIVITY_OBSERVED, observed.append)
        ActivityController(
            bus,
            BehaviorConfig(enabled=False),
            initial_time=_start(),
        )

        bus.publish(EventType.CHAT_OPEN_REQUESTED)

        self.assertEqual(observed, [])

    def test_config_update_changes_idle_thresholds(self) -> None:
        bus = EventBus()
        controller = ActivityController(
            bus,
            BehaviorConfig(idle_after_seconds=300, away_after_seconds=900),
            initial_time=_start(),
        )

        controller.apply_config(
            BehaviorConfig(idle_after_seconds=60, away_after_seconds=120)
        )
        snapshot = controller.tick(_start() + timedelta(seconds=60))

        self.assertEqual(snapshot.state, ActivityState.IDLE)


def _start() -> datetime:
    return datetime(2026, 7, 24, 10, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
