"""Application-level bridge from companion mood to pet animation."""

from __future__ import annotations

from project_akiha.core.behavior import CompanionMood, MoodAnimationMapper
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationState


class MoodAnimationController:
    """Request pet animation changes from mood without overriding user control."""

    def __init__(
        self,
        event_bus: EventBus,
        mapper: MoodAnimationMapper,
        initial_animation_state: AnimationState = AnimationState.IDLE,
    ) -> None:
        self._event_bus = event_bus
        self._mapper = mapper
        self._current_animation_state = initial_animation_state
        self._sleeping_from_mood = False
        self._pending_mood_sleep = False

        event_bus.subscribe(EventType.MOOD_STATE_CHANGED, self._handle_mood_changed)
        event_bus.subscribe(EventType.STATE_CHANGED, self._handle_animation_changed)

    @property
    def sleeping_from_mood(self) -> bool:
        """Return whether the current sleep state was requested by mood."""
        return self._sleeping_from_mood

    def _handle_mood_changed(self, event: Event) -> None:
        mood_value = event.payload.get("mood")
        reason = event.payload.get("reason")
        if not isinstance(mood_value, str):
            return
        if reason == "wake_requested":
            return

        try:
            mood = CompanionMood(mood_value)
        except ValueError:
            return

        decision = self._mapper.decide(
            mood=mood,
            current_animation_state=self._current_animation_state,
            sleeping_from_mood=self._sleeping_from_mood,
        )
        if decision.animation_state is None:
            return

        if decision.animation_state == AnimationState.SLEEPING:
            self._pending_mood_sleep = decision.mood_driven_sleep
            self._event_bus.publish(EventType.PET_SLEEP_REQUESTED)
        elif decision.animation_state == AnimationState.IDLE:
            self._sleeping_from_mood = False
            self._event_bus.publish(EventType.PET_WAKE_REQUESTED)

    def _handle_animation_changed(self, event: Event) -> None:
        state_value = event.payload.get("state")
        if not isinstance(state_value, str):
            return

        try:
            next_state = AnimationState(state_value)
        except ValueError:
            return

        self._current_animation_state = next_state
        if next_state == AnimationState.SLEEPING:
            self._sleeping_from_mood = self._pending_mood_sleep
            self._pending_mood_sleep = False
            return

        self._pending_mood_sleep = False
        self._sleeping_from_mood = False
