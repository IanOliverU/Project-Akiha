"""Tests for deterministic autonomous activity selection."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.pet import PetState
from project_akiha.core.pet_activity import (
    PetActivityContext,
    PetActivityId,
    PetActivityScheduler,
    load_pet_activity_manifest,
)
from project_akiha.core.state.animation import AnimationState


class PetActivitySchedulerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.definitions = load_pet_activity_manifest(
            Path("assets/animations/activities.toml")
        )
        self.scheduler = PetActivityScheduler(self.definitions)

    def test_selects_wander_for_idle_waiting_user(self) -> None:
        decision = self.scheduler.select(_context())

        self.assertEqual(decision.definition.activity_id, PetActivityId.WANDER)

    def test_cooldown_falls_back_to_quiet_idle(self) -> None:
        now = _now()
        self.scheduler.mark_finished(PetActivityId.WANDER, now)

        decision = self.scheduler.select(_context(now=now + timedelta(seconds=5)))

        self.assertEqual(decision.definition.activity_id, PetActivityId.QUIET_IDLE)

    def test_sleepy_context_selects_rest(self) -> None:
        decision = self.scheduler.select(
            _context(
                user_activity=ActivityState.AWAY,
                mood=CompanionMood.RESTING,
            )
        )

        self.assertEqual(decision.definition.activity_id, PetActivityId.REST)

    def test_active_user_and_busy_animation_fail_closed(self) -> None:
        active = self.scheduler.select(_context(user_activity=ActivityState.ACTIVE))
        busy = self.scheduler.select(_context(animation_state=AnimationState.WALKING))

        self.assertIsNone(active.definition)
        self.assertEqual(active.reason, "no_eligible_activity")
        self.assertIsNone(busy.definition)
        self.assertEqual(busy.reason, "animation_busy")


def _context(
    *,
    now: datetime | None = None,
    user_activity: ActivityState = ActivityState.IDLE,
    mood: CompanionMood = CompanionMood.WAITING,
    animation_state: AnimationState = AnimationState.IDLE,
) -> PetActivityContext:
    return PetActivityContext(
        now=now or _now(),
        user_activity=user_activity,
        mood=mood,
        pet_state=PetState.initial(),
        animation_state=animation_state,
    )


def _now() -> datetime:
    return datetime(2026, 8, 22, 4, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
