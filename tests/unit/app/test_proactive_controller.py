"""Tests for app-level proactive suggestion publishing."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.app.proactive_controller import ProactiveController
from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ProactiveSuggestionEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ProactiveControllerTest(unittest.TestCase):
    """Verify proactive suggestions are emitted through the app event bus."""

    def test_idle_state_change_publishes_suggestion_when_allowed(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        ProactiveController(bus, _engine(proactive_enabled=True))

        bus.publish(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            _activity(ActivityState.IDLE).payload,
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].payload["kind"], "idle_check_in")
        self.assertEqual(suggestions[0].payload["activity_state"], "idle")

    def test_active_state_change_does_not_publish_suggestion(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        ProactiveController(bus, _engine(proactive_enabled=True))

        bus.publish(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            _activity(ActivityState.ACTIVE).payload,
        )

        self.assertEqual(suggestions, [])

    def test_invalid_activity_payload_is_ignored(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        ProactiveController(bus, _engine(proactive_enabled=True))

        bus.publish(EventType.USER_ACTIVITY_STATE_CHANGED, {"state": "idle"})

        self.assertEqual(suggestions, [])

    def test_direct_snapshot_evaluation_publishes_suggestion(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        controller = ProactiveController(bus, _engine(proactive_enabled=True))

        suggestion = controller.evaluate_snapshot(
            _activity(ActivityState.IDLE).snapshot,
            now=_now(),
        )

        self.assertIsNotNone(suggestion)
        self.assertEqual(len(suggestions), 1)


def _engine(proactive_enabled: bool) -> ProactiveSuggestionEngine:
    return ProactiveSuggestionEngine(
        NotificationPolicy(BehaviorConfig(proactive_enabled=proactive_enabled))
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


class _ActivityFixture:
    def __init__(self, state: ActivityState) -> None:
        self.snapshot = ActivitySnapshot(
            state=state,
            idle_seconds=300,
            last_activity_at=_now() - timedelta(seconds=300),
            source="test",
        )

    @property
    def payload(self) -> dict[str, object]:
        return {
            "state": self.snapshot.state.value,
            "idle_seconds": self.snapshot.idle_seconds,
            "last_activity_at": self.snapshot.last_activity_at.isoformat(),
            "source": self.snapshot.source,
        }


def _activity(state: ActivityState) -> _ActivityFixture:
    return _ActivityFixture(state)


if __name__ == "__main__":
    unittest.main()
