"""Tests for companion mood state derivation."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    CompanionMood,
    MoodEngine,
)


class MoodEngineTest(unittest.TestCase):
    """Verify deterministic mood transitions from behavior signals."""

    def test_starts_calm(self) -> None:
        engine = MoodEngine(initial_time=_now())

        self.assertEqual(engine.snapshot.mood, CompanionMood.CALM)
        self.assertEqual(engine.snapshot.reason, "startup")
        self.assertEqual(engine.snapshot.updated_at, _now())

    def test_activity_states_map_to_moods(self) -> None:
        engine = MoodEngine(initial_time=_now())

        active = engine.observe_activity(_activity(ActivityState.ACTIVE, "chat"))
        idle = engine.observe_activity(_activity(ActivityState.IDLE, "chat"))
        away = engine.observe_activity(_activity(ActivityState.AWAY, "chat"))

        self.assertEqual(active.mood, CompanionMood.ATTENTIVE)
        self.assertEqual(active.reason, "chat")
        self.assertEqual(idle.mood, CompanionMood.WAITING)
        self.assertEqual(idle.reason, "user_idle")
        self.assertEqual(away.mood, CompanionMood.RESTING)
        self.assertEqual(away.reason, "user_away")

    def test_sleep_and_wake_update_mood(self) -> None:
        engine = MoodEngine(initial_time=_now())

        sleepy = engine.observe_sleep_requested(_now())
        awake = engine.observe_wake_requested(_now() + timedelta(seconds=1))

        self.assertEqual(sleepy.mood, CompanionMood.SLEEPY)
        self.assertEqual(awake.mood, CompanionMood.ATTENTIVE)

    def test_delivery_result_updates_mood(self) -> None:
        engine = MoodEngine(initial_time=_now())

        checking_in = engine.observe_delivery_result(
            delivered=True,
            reason="chat_visible",
            now=_now(),
        )
        calm = engine.observe_delivery_result(
            delivered=False,
            reason="no_available_surface",
            now=_now() + timedelta(seconds=1),
        )

        self.assertEqual(checking_in.mood, CompanionMood.CHECKING_IN)
        self.assertEqual(checking_in.reason, "chat_visible")
        self.assertEqual(calm.mood, CompanionMood.CALM)
        self.assertEqual(calm.reason, "no_available_surface")


def _activity(state: ActivityState, source: str) -> ActivitySnapshot:
    return ActivitySnapshot(
        state=state,
        idle_seconds=300,
        last_activity_at=_now(),
        source=source,
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
