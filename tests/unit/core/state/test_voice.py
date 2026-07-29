"""Tests for the Phase 7 voice state machine."""

from __future__ import annotations

import unittest

from project_akiha.core.state.voice import (
    InvalidVoiceTransitionError,
    VoiceState,
    VoiceStateMachine,
)


class VoiceStateMachineTest(unittest.TestCase):
    """Verify explicit voice activity transitions."""

    def test_starts_idle_by_default(self) -> None:
        state_machine = VoiceStateMachine()

        self.assertEqual(state_machine.state, VoiceState.IDLE)

    def test_allows_push_to_talk_flow(self) -> None:
        state_machine = VoiceStateMachine()

        state_machine.transition_to(VoiceState.LISTENING)
        state_machine.transition_to(VoiceState.THINKING)
        result = state_machine.transition_to(VoiceState.SPEAKING)

        self.assertEqual(result, VoiceState.SPEAKING)

    def test_allows_recovery_from_error(self) -> None:
        state_machine = VoiceStateMachine(VoiceState.ERROR)

        result = state_machine.transition_to(VoiceState.IDLE)

        self.assertEqual(result, VoiceState.IDLE)

    def test_rejects_listening_while_muted(self) -> None:
        state_machine = VoiceStateMachine(VoiceState.MUTED)

        with self.assertRaises(InvalidVoiceTransitionError):
            state_machine.transition_to(VoiceState.LISTENING)


if __name__ == "__main__":
    unittest.main()
