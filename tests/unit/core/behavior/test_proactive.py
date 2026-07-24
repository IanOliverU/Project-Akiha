"""Tests for proactive companion suggestion generation."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ProactiveSuggestionEngine,
)


class ProactiveSuggestionEngineTest(unittest.TestCase):
    """Verify activity snapshots produce conservative suggestions."""

    def test_returns_no_suggestion_for_active_user(self) -> None:
        engine = _engine(proactive_enabled=True)

        suggestion = engine.evaluate_activity(_activity(ActivityState.ACTIVE), _now())

        self.assertIsNone(suggestion)

    def test_returns_idle_check_in_when_policy_allows(self) -> None:
        engine = _engine(proactive_enabled=True)

        suggestion = engine.evaluate_activity(_activity(ActivityState.IDLE), _now())

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.kind, "idle_check_in")
        self.assertEqual(suggestion.activity_state, ActivityState.IDLE)
        self.assertEqual(suggestion.idle_seconds, 300)
        self.assertEqual(engine.last_suggestion_at, _now())

    def test_returns_no_suggestion_when_proactive_behavior_disabled(self) -> None:
        engine = _engine(proactive_enabled=False)

        suggestion = engine.evaluate_activity(_activity(ActivityState.IDLE), _now())

        self.assertIsNone(suggestion)

    def test_respects_notification_cooldown(self) -> None:
        engine = _engine(proactive_enabled=True, cooldown_seconds=600)

        first = engine.evaluate_activity(_activity(ActivityState.IDLE), _now())
        second = engine.evaluate_activity(
            _activity(ActivityState.IDLE),
            _now() + timedelta(seconds=599),
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)


def _engine(
    *,
    proactive_enabled: bool,
    cooldown_seconds: int = 1800,
) -> ProactiveSuggestionEngine:
    return ProactiveSuggestionEngine(
        NotificationPolicy(
            BehaviorConfig(
                proactive_enabled=proactive_enabled,
                minimum_seconds_between_notifications=cooldown_seconds,
            )
        )
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _activity(state: ActivityState) -> ActivitySnapshot:
    return ActivitySnapshot(
        state=state,
        idle_seconds=300,
        last_activity_at=_now() - timedelta(seconds=300),
        source="test",
    )


if __name__ == "__main__":
    unittest.main()
