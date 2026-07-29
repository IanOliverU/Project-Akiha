"""Tests for the framework-free event bus."""

from __future__ import annotations

import unittest

from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class EventBusTest(unittest.TestCase):
    """Verify event subscription and publishing behavior."""

    def test_publish_sends_event_to_subscriber(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        bus.subscribe(EventType.PET_DRAGGED, received.append)
        bus.publish(EventType.PET_DRAGGED, {"x": 10, "y": 20})

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].event_type, EventType.PET_DRAGGED)
        self.assertEqual(received[0].payload, {"x": 10, "y": 20})

    def test_unsubscribe_removes_handler(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        bus.subscribe(EventType.PET_DRAGGED, received.append)
        bus.unsubscribe(EventType.PET_DRAGGED, received.append)
        bus.publish(EventType.PET_DRAGGED)

        self.assertEqual(received, [])

    def test_voice_state_event_uses_canonical_event_bus(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        bus.subscribe(EventType.VOICE_STATE_CHANGED, received.append)
        bus.publish(EventType.VOICE_STATE_CHANGED, {"state": "listening"})

        self.assertEqual(received[0].event_type, EventType.VOICE_STATE_CHANGED)
        self.assertEqual(received[0].payload, {"state": "listening"})

    def test_voice_replay_event_uses_canonical_event_bus(self) -> None:
        bus = EventBus()
        received: list[Event] = []

        bus.subscribe(EventType.VOICE_REPLAY_REQUESTED, received.append)
        bus.publish(EventType.VOICE_REPLAY_REQUESTED)

        self.assertEqual(received[0].event_type, EventType.VOICE_REPLAY_REQUESTED)


if __name__ == "__main__":
    unittest.main()
