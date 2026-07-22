"""Animation state machine for the Phase 1 desktop pet."""

from __future__ import annotations

from enum import StrEnum


class AnimationState(StrEnum):
    """Supported pet animation states."""

    IDLE = "idle"
    WALKING = "walking"
    DRAGGING = "dragging"
    SLEEPING = "sleeping"


class InvalidAnimationTransitionError(ValueError):
    """Raised when an animation transition is not allowed."""


class AnimationStateMachine:
    """Keep pet animation transitions explicit and testable."""

    _allowed_transitions: dict[AnimationState, frozenset[AnimationState]] = {
        AnimationState.IDLE: frozenset(
            {
                AnimationState.WALKING,
                AnimationState.DRAGGING,
                AnimationState.SLEEPING,
            }
        ),
        AnimationState.WALKING: frozenset(
            {AnimationState.IDLE, AnimationState.DRAGGING}
        ),
        AnimationState.DRAGGING: frozenset(
            {AnimationState.IDLE, AnimationState.WALKING}
        ),
        AnimationState.SLEEPING: frozenset({AnimationState.IDLE}),
    }

    def __init__(self, initial_state: AnimationState = AnimationState.IDLE) -> None:
        self._state = initial_state

    @property
    def state(self) -> AnimationState:
        """Return the current animation state."""
        return self._state

    def can_transition_to(self, next_state: AnimationState) -> bool:
        """Return whether the requested transition is valid."""
        return (
            next_state == self._state
            or next_state in self._allowed_transitions[self._state]
        )

    def transition_to(self, next_state: AnimationState) -> AnimationState:
        """Move to the next animation state if the transition is valid."""
        if not self.can_transition_to(next_state):
            message = f"Cannot transition from {self._state} to {next_state}."
            raise InvalidAnimationTransitionError(message)

        self._state = next_state
        return self._state
