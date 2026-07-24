"""Tests for app-level companion mood wiring."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.app.mood_controller import MoodController
from project_akiha.core.behavior import MoodEngine
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class MoodControllerTest(unittest.TestCase):
    """Verify app events publish companion mood changes."""

    def test_publishes_initial_mood(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.MOOD_STATE_CHANGED, received.append)

        MoodController(bus, MoodEngine(initial_time=_now()))

        self.assertEqual(received[-1].payload["mood"], "calm")
        self.assertEqual(received[-1].payload["reason"], "startup")

    def test_activity_state_change_updates_mood(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.MOOD_STATE_CHANGED, received.append)
        MoodController(bus, MoodEngine(initial_time=_now()))

        bus.publish(EventType.USER_ACTIVITY_STATE_CHANGED, _activity_payload("idle"))

        self.assertEqual(received[-1].payload["mood"], "waiting")
        self.assertEqual(received[-1].payload["reason"], "user_idle")

    def test_proactive_delivery_updates_mood(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.MOOD_STATE_CHANGED, received.append)
        MoodController(bus, MoodEngine(initial_time=_now()))

        bus.publish(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            {
                "delivered": True,
                "reason": "chat_visible",
            },
        )

        self.assertEqual(received[-1].payload["mood"], "checking_in")
        self.assertEqual(received[-1].payload["reason"], "chat_visible")

    def test_sleep_and_wake_events_update_mood(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.MOOD_STATE_CHANGED, received.append)
        MoodController(bus, MoodEngine(initial_time=_now()))

        bus.publish(EventType.PET_SLEEP_REQUESTED)
        self.assertEqual(received[-1].payload["mood"], "sleepy")

        bus.publish(EventType.PET_WAKE_REQUESTED)
        self.assertEqual(received[-1].payload["mood"], "attentive")

    def test_repeated_same_mood_and_reason_is_not_republished(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.MOOD_STATE_CHANGED, received.append)
        MoodController(bus, MoodEngine(initial_time=_now()))

        bus.publish(EventType.USER_ACTIVITY_STATE_CHANGED, _activity_payload("idle"))
        bus.publish(EventType.USER_ACTIVITY_STATE_CHANGED, _activity_payload("idle"))

        self.assertEqual(len(received), 2)

    def test_invalid_activity_payload_is_ignored(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.MOOD_STATE_CHANGED, received.append)
        MoodController(bus, MoodEngine(initial_time=_now()))

        bus.publish(EventType.USER_ACTIVITY_STATE_CHANGED, {"state": "idle"})

        self.assertEqual(len(received), 1)


def _activity_payload(state: str) -> dict[str, object]:
    return {
        "state": state,
        "idle_seconds": 300,
        "last_activity_at": _now().isoformat(),
        "source": "test",
    }


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
