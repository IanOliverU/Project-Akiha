"""Application controller for Phase 1 pet behavior."""

from __future__ import annotations

from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import (
    AnimationSequenceId,
    AnimationState,
    AnimationStateMachine,
    InvalidAnimationTransitionError,
)
from project_akiha.core.state.voice import VoiceState


class PetController:
    """Translate pet UI events into framework-free state transitions."""

    def __init__(
        self,
        event_bus: EventBus,
        animation_state: AnimationStateMachine,
    ) -> None:
        self._event_bus = event_bus
        self._animation_state = animation_state
        self._staged_sleep_enabled = False
        self._pending_after_wake: AnimationState | None = None

        event_bus.subscribe(EventType.PET_DRAG_STARTED, self._handle_drag_started)
        event_bus.subscribe(EventType.PET_DRAG_ENDED, self._handle_drag_ended)
        event_bus.subscribe(EventType.PET_WALK_REQUESTED, self._handle_walk_requested)
        event_bus.subscribe(EventType.PET_IDLE_REQUESTED, self._handle_idle_requested)
        event_bus.subscribe(EventType.PET_SLEEP_REQUESTED, self._handle_sleep_requested)
        event_bus.subscribe(EventType.PET_WAKE_REQUESTED, self._handle_wake_requested)
        event_bus.subscribe(EventType.VOICE_STATE_CHANGED, self._handle_voice_changed)
        for event_type in (
            EventType.PET_CARE_OPEN_REQUESTED,
            EventType.PET_CARE_COMPLETED,
            EventType.CHAT_OPEN_REQUESTED,
            EventType.SETTINGS_OPEN_REQUESTED,
            EventType.PET_STATUS_OPEN_REQUESTED,
        ):
            event_bus.subscribe(event_type, self._handle_high_priority_interaction)
        event_bus.subscribe(
            EventType.ANIMATION_SEQUENCE_COMPLETED,
            self._handle_animation_sequence_completed,
        )

        self._publish_state()

    @property
    def animation_state(self) -> AnimationState:
        """Return the current pet animation state."""
        return self._animation_state.state

    @property
    def staged_sleep_enabled(self) -> bool:
        """Return whether complete approved sleep and wake sequences are active."""
        return self._staged_sleep_enabled

    def set_staged_sleep_enabled(self, enabled: bool) -> None:
        """Enable staged sleep only when the active appearance supports both paths."""
        self._staged_sleep_enabled = bool(enabled)
        if (
            not self._staged_sleep_enabled
            and self.animation_state is AnimationState.WAKING
        ):
            self._pending_after_wake = None
            self._transition_to(AnimationState.IDLE)

    def _handle_drag_started(self, event: Event) -> None:
        del event
        if self._animation_state.state in {
            AnimationState.SLEEPING,
            AnimationState.WAKING,
        }:
            self._begin_wake(AnimationState.DRAGGING)
            return
        self._transition_to(AnimationState.DRAGGING)

    def _handle_drag_ended(self, event: Event) -> None:
        del event
        if self._animation_state.state is AnimationState.WAKING:
            self._pending_after_wake = AnimationState.IDLE
            return
        self._transition_to(AnimationState.IDLE)

    def _handle_walk_requested(self, event: Event) -> None:
        del event
        if self._animation_state.state in {
            AnimationState.SLEEPING,
            AnimationState.WAKING,
        }:
            self._begin_wake(AnimationState.WALKING)
            return
        self._transition_to(AnimationState.WALKING)

    def _handle_idle_requested(self, event: Event) -> None:
        del event
        if self._animation_state.state in {
            AnimationState.SLEEPING,
            AnimationState.WAKING,
        }:
            self._begin_wake(AnimationState.IDLE)
            return
        self._transition_to(AnimationState.IDLE)

    def _handle_sleep_requested(self, event: Event) -> None:
        del event
        self._pending_after_wake = None
        if self._animation_state.state in {
            AnimationState.WALKING,
            AnimationState.DRAGGING,
            AnimationState.WAKING,
        }:
            self._transition_to(AnimationState.IDLE)
        self._transition_to(AnimationState.SLEEPING)

    def _handle_wake_requested(self, event: Event) -> None:
        del event
        self._begin_wake(AnimationState.IDLE)

    def _handle_voice_changed(self, event: Event) -> None:
        state_value = event.payload.get("state")
        if not isinstance(state_value, str):
            return
        try:
            state = VoiceState(state_value)
        except ValueError:
            return
        if state in {VoiceState.LISTENING, VoiceState.THINKING, VoiceState.SPEAKING}:
            self._handle_high_priority_interaction(event)

    def _handle_high_priority_interaction(self, event: Event) -> None:
        del event
        if self._animation_state.state in {
            AnimationState.SLEEPING,
            AnimationState.WAKING,
        }:
            self._begin_wake(AnimationState.IDLE)

    def _handle_animation_sequence_completed(self, event: Event) -> None:
        if event.payload.get("sequence_id") != AnimationSequenceId.WAKE.value:
            return
        if self._animation_state.state is not AnimationState.WAKING:
            return
        next_state = self._pending_after_wake or AnimationState.IDLE
        self._pending_after_wake = None
        self._transition_to(next_state)

    def _begin_wake(self, next_state: AnimationState) -> None:
        current_state = self._animation_state.state
        if current_state is AnimationState.WAKING:
            self._pending_after_wake = next_state
            return
        if current_state is not AnimationState.SLEEPING:
            self._transition_to(next_state)
            return
        if self._staged_sleep_enabled:
            self._pending_after_wake = next_state
            self._transition_to(AnimationState.WAKING)
            return
        self._transition_to(AnimationState.IDLE)
        if next_state is not AnimationState.IDLE:
            self._transition_to(next_state)

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
