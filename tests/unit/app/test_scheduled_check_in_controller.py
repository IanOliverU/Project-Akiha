"""Tests for app-level scheduled check-in publishing."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.app.scheduled_check_in_controller import ScheduledCheckInController
from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ScheduledCheckInEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ScheduledCheckInControllerTest(unittest.TestCase):
    """Verify scheduled check-ins enter the proactive delivery pipeline."""

    def test_due_check_in_publishes_proactive_suggestion(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        controller = ScheduledCheckInController(
            bus,
            _engine(initial_time=_now()),
        )

        suggestion = controller.tick(_activity(), _now() + timedelta(seconds=3600))

        self.assertIsNotNone(suggestion)
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].payload["kind"], "scheduled_check_in")
        self.assertEqual(suggestions[0].payload["activity_state"], "active")

    def test_not_due_check_in_does_not_publish(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        controller = ScheduledCheckInController(
            bus,
            _engine(initial_time=_now()),
        )

        suggestion = controller.tick(_activity(), _now() + timedelta(seconds=30))

        self.assertIsNone(suggestion)
        self.assertEqual(suggestions, [])


def _engine(initial_time: datetime) -> ScheduledCheckInEngine:
    config = BehaviorConfig(
        proactive_enabled=True,
        scheduled_check_ins_enabled=True,
        scheduled_check_in_interval_seconds=3600,
    )
    return ScheduledCheckInEngine(
        NotificationPolicy(config),
        config,
        initial_time=initial_time,
    )


def _activity() -> ActivitySnapshot:
    return ActivitySnapshot(
        state=ActivityState.ACTIVE,
        idle_seconds=0,
        last_activity_at=_now(),
        source="test",
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
