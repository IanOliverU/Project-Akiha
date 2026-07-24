"""Tests for mood-to-animation mapping."""

from __future__ import annotations

import unittest

from project_akiha.core.behavior import CompanionMood, MoodAnimationMapper
from project_akiha.core.state.animation import AnimationState


class MoodAnimationMapperTest(unittest.TestCase):
    """Verify mood animation decisions stay conservative."""

    def test_resting_mood_requests_sleep_from_idle(self) -> None:
        decision = MoodAnimationMapper().decide(
            mood=CompanionMood.RESTING,
            current_animation_state=AnimationState.IDLE,
            sleeping_from_mood=False,
        )

        self.assertEqual(decision.animation_state, AnimationState.SLEEPING)
        self.assertTrue(decision.mood_driven_sleep)
        self.assertEqual(decision.reason, "mood_resting")

    def test_resting_mood_does_not_interrupt_walking(self) -> None:
        decision = MoodAnimationMapper().decide(
            mood=CompanionMood.RESTING,
            current_animation_state=AnimationState.WALKING,
            sleeping_from_mood=False,
        )

        self.assertIsNone(decision.animation_state)
        self.assertEqual(decision.reason, "busy")

    def test_attentive_mood_wakes_only_mood_driven_sleep(self) -> None:
        decision = MoodAnimationMapper().decide(
            mood=CompanionMood.ATTENTIVE,
            current_animation_state=AnimationState.SLEEPING,
            sleeping_from_mood=True,
        )

        self.assertEqual(decision.animation_state, AnimationState.IDLE)
        self.assertFalse(decision.mood_driven_sleep)

    def test_attentive_mood_does_not_wake_manual_sleep(self) -> None:
        decision = MoodAnimationMapper().decide(
            mood=CompanionMood.ATTENTIVE,
            current_animation_state=AnimationState.SLEEPING,
            sleeping_from_mood=False,
        )

        self.assertIsNone(decision.animation_state)
        self.assertEqual(decision.reason, "no_change")


if __name__ == "__main__":
    unittest.main()
