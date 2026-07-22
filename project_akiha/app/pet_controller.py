"""Application controller for Phase 1 pet behavior."""

from __future__ import annotations

from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import (
    AnimationState,
    AnimationStateMachine,
    InvalidAnimationTransitionError,
)


class PetController:
    """Translate pet UI events into framework-free state transitions."""

    def __init__(
        self,
        event_bus: EventBus,
        animation_state: AnimationStateMachine,
    ) -> None:
        self._event_bus = event_bus
        self._animation_state = animation_state

        event_bus.subscribe(EventType.PET_DRAG_STARTED, self._handle_drag_started)
        event_bus.subscribe(EventType.PET_DRAG_ENDED, self._handle_drag_ended)

        self._publish_state()

    @property
    def animation_state(self) -> AnimationState:
        """Return the current pet animation state."""
        return self._animation_state.state

    def _handle_drag_started(self, event: Event) -> None:
        del event
        self._transition_to(AnimationState.DRAGGING)

    def _handle_drag_ended(self, event: Event) -> None:
        del event
        self._transition_to(AnimationState.IDLE)

    def _transition_to(self, next_state: AnimationState) -> None:
        previous_state = self._animation_state.state
        try:
            current_state = self._animation_state.transition_to(next_state)
        except InvalidAnimationTransitionError as error:
            self._event_bus.publish(
                EventType.ERROR_OCCURRED,
                {
                    "source": "pet_controller",
                    "message": str(error),
                },
            )
            return

        if current_state != previous_state:
            self._publish_state()

    def _publish_state(self) -> None:
        self._event_bus.publish(
            EventType.STATE_CHANGED,
            {"state": self._animation_state.state.value},
        )
