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

    def test_sleeping_can_enter_staged_wake(self) -> None:
        state_machine = AnimationStateMachine(AnimationState.SLEEPING)

        result = state_machine.transition_to(AnimationState.WAKING)

        self.assertEqual(result, AnimationState.WAKING)

    def test_waking_can_finish_in_requested_direct_state(self) -> None:
        for state in (
            AnimationState.IDLE,
            AnimationState.WALKING,
            AnimationState.DRAGGING,
        ):
            with self.subTest(state=state):
                state_machine = AnimationStateMachine(AnimationState.WAKING)
                self.assertEqual(state_machine.transition_to(state), state)


if __name__ == "__main__":
    unittest.main()
