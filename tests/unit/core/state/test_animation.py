"""Tests for the animation state machine."""

from __future__ import annotations

import unittest

from project_akiha.core.state.animation import (
    AnimationState,
    AnimationStateMachine,
    InvalidAnimationTransitionError,
)


class AnimationStateMachineTest(unittest.TestCase):
    """Verify allowed and rejected animation transitions."""

    def test_starts_idle_by_default(self) -> None:
        state_machine = AnimationStateMachine()

        self.assertEqual(state_machine.state, AnimationState.IDLE)

    def test_allows_dragging_from_idle(self) -> None:
        state_machine = AnimationStateMachine()

        result = state_machine.transition_to(AnimationState.DRAGGING)

        self.assertEqual(result, AnimationState.DRAGGING)

    def test_rejects_sleeping_to_dragging(self) -> None:
        state_machine = AnimationStateMachine(AnimationState.SLEEPING)

        with self.assertRaises(InvalidAnimationTransitionError):
            state_machine.transition_to(AnimationState.DRAGGING)


if __name__ == "__main__":
    unittest.main()
