"""Framework-free state model for Phase 7 voice activity."""

from __future__ import annotations

from enum import StrEnum


class VoiceState(StrEnum):
    """User-visible voice activity states."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    MUTED = "muted"
    ERROR = "error"


class InvalidVoiceTransitionError(ValueError):
    """Raised when a voice state transition is not allowed."""


class VoiceStateMachine:
    """Keep voice activity transitions explicit and independently testable."""

    _allowed_transitions: dict[VoiceState, frozenset[VoiceState]] = {
        VoiceState.IDLE: frozenset(
            {
                VoiceState.LISTENING,
                VoiceState.THINKING,
                VoiceState.SPEAKING,
                VoiceState.MUTED,
                VoiceState.ERROR,
            }
        ),
        VoiceState.LISTENING: frozenset(
            {
                VoiceState.IDLE,
                VoiceState.THINKING,
                VoiceState.MUTED,
                VoiceState.ERROR,
            }
        ),
        VoiceState.THINKING: frozenset(
            {
                VoiceState.IDLE,
                VoiceState.SPEAKING,
                VoiceState.MUTED,
                VoiceState.ERROR,
            }
        ),
        VoiceState.SPEAKING: frozenset(
            {
                VoiceState.IDLE,
                VoiceState.THINKING,
                VoiceState.MUTED,
                VoiceState.ERROR,
            }
        ),
        VoiceState.MUTED: frozenset({VoiceState.IDLE, VoiceState.ERROR}),
        VoiceState.ERROR: frozenset({VoiceState.IDLE, VoiceState.MUTED}),
    }

    def __init__(self, initial_state: VoiceState = VoiceState.IDLE) -> None:
        self._state = initial_state

    @property
    def state(self) -> VoiceState:
        """Return the current voice state."""
        return self._state

    def can_transition_to(self, next_state: VoiceState) -> bool:
        """Return whether the requested transition is valid."""
        return (
            next_state == self._state
            or next_state in self._allowed_transitions[self._state]
        )

    def transition_to(self, next_state: VoiceState) -> VoiceState:
        """Move to the next voice state if the transition is valid."""
        if not self.can_transition_to(next_state):
            message = f"Cannot transition from {self._state} to {next_state}."
            raise InvalidVoiceTransitionError(message)

        self._state = next_state
        return self._state
