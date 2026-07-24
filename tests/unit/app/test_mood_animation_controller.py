"""Tests for app-level mood-to-animation wiring."""

from __future__ import annotations

import unittest

from project_akiha.app.mood_animation_controller import MoodAnimationController
from project_akiha.core.behavior import MoodAnimationMapper
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationState


class MoodAnimationControllerTest(unittest.TestCase):
    """Verify mood events request safe pet animation changes."""

    def test_resting_mood_requests_sleep_from_idle(self) -> None:
        bus = EventBus()
        sleep_requests: list[Event] = []
        bus.subscribe(EventType.PET_SLEEP_REQUESTED, sleep_requests.append)
        MoodAnimationController(bus, MoodAnimationMapper())

        bus.publish(EventType.MOOD_STATE_CHANGED, _mood("resting"))

        self.assertEqual(len(sleep_requests), 1)

    def test_resting_mood_does_not_interrupt_walking(self) -> None:
        bus = EventBus()
        sleep_requests: list[Event] = []
        bus.subscribe(EventType.PET_SLEEP_REQUESTED, sleep_requests.append)
        MoodAnimationController(
            bus,
            MoodAnimationMapper(),
            initial_animation_state=AnimationState.WALKING,
        )

        bus.publish(EventType.MOOD_STATE_CHANGED, _mood("resting"))

        self.assertEqual(sleep_requests, [])

    def test_mood_driven_sleep_wakes_when_mood_becomes_attentive(self) -> None:
        bus = EventBus()
        wake_requests: list[Event] = []
        bus.subscribe(EventType.PET_WAKE_REQUESTED, wake_requests.append)
        controller = MoodAnimationController(bus, MoodAnimationMapper())

        bus.publish(EventType.MOOD_STATE_CHANGED, _mood("resting"))
        bus.publish(EventType.STATE_CHANGED, {"state": "sleeping"})
        bus.publish(EventType.MOOD_STATE_CHANGED, _mood("attentive"))

        self.assertFalse(controller.sleeping_from_mood)
        self.assertEqual(len(wake_requests), 1)

    def test_manual_sleep_is_not_woken_by_attentive_mood(self) -> None:
        bus = EventBus()
        wake_requests: list[Event] = []
        bus.subscribe(EventType.PET_WAKE_REQUESTED, wake_requests.append)
        controller = MoodAnimationController(bus, MoodAnimationMapper())

        bus.publish(EventType.STATE_CHANGED, {"state": "sleeping"})
        bus.publish(EventType.MOOD_STATE_CHANGED, _mood("attentive"))

        self.assertFalse(controller.sleeping_from_mood)
        self.assertEqual(wake_requests, [])

    def test_wake_requested_mood_reason_does_not_duplicate_wake_request(self) -> None:
        bus = EventBus()
        wake_requests: list[Event] = []
        bus.subscribe(EventType.PET_WAKE_REQUESTED, wake_requests.append)
        controller = MoodAnimationController(bus, MoodAnimationMapper())

        bus.publish(EventType.MOOD_STATE_CHANGED, _mood("resting"))
        bus.publish(EventType.STATE_CHANGED, {"state": "sleeping"})
        bus.publish(
            EventType.MOOD_STATE_CHANGED,
            _mood("attentive", reason="wake_requested"),
        )

        self.assertTrue(controller.sleeping_from_mood)
        self.assertEqual(wake_requests, [])

    def test_invalid_payload_is_ignored(self) -> None:
        bus = EventBus()
        sleep_requests: list[Event] = []
        bus.subscribe(EventType.PET_SLEEP_REQUESTED, sleep_requests.append)
        MoodAnimationController(bus, MoodAnimationMapper())

        bus.publish(EventType.MOOD_STATE_CHANGED, {"mood": "unknown"})
        bus.publish(EventType.STATE_CHANGED, {"state": "unknown"})

        self.assertEqual(sleep_requests, [])


def _mood(mood: str, reason: str = "test") -> dict[str, object]:
    return {
        "mood": mood,
        "reason": reason,
        "updated_at": "2026-07-24T12:00:00+00:00",
    }


if __name__ == "__main__":
    unittest.main()
