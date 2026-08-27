"""Tests for the Phase 1 pet controller."""

from __future__ import annotations

import unittest

from project_akiha.app.pet_controller import PetController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import (
    AnimationSequenceId,
    AnimationState,
    AnimationStateMachine,
)
from project_akiha.core.state.voice import VoiceState


class PetControllerTest(unittest.TestCase):
    """Verify UI events drive animation state through the controller."""

    def test_publishes_initial_state(self) -> None:
        bus = EventBus()
        received: list[Event] = []
        bus.subscribe(EventType.STATE_CHANGED, received.append)

        PetController(bus, AnimationStateMachine())

        self.assertEqual(received[-1].payload, {"state": "idle"})

    def test_drag_events_change_animation_state(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())

        bus.publish(EventType.PET_DRAG_STARTED)
        self.assertEqual(controller.animation_state, AnimationState.DRAGGING)

        bus.publish(EventType.PET_DRAG_ENDED)
        self.assertEqual(controller.animation_state, AnimationState.IDLE)

    def test_walk_and_idle_events_change_animation_state(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())

        bus.publish(EventType.PET_WALK_REQUESTED)
        self.assertEqual(controller.animation_state, AnimationState.WALKING)

        bus.publish(EventType.PET_IDLE_REQUESTED)
        self.assertEqual(controller.animation_state, AnimationState.IDLE)

    def test_sleep_and_wake_events_change_animation_state(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())

        bus.publish(EventType.PET_SLEEP_REQUESTED)
        self.assertEqual(controller.animation_state, AnimationState.SLEEPING)

        bus.publish(EventType.PET_WAKE_REQUESTED)
        self.assertEqual(controller.animation_state, AnimationState.IDLE)

    def test_direct_sleep_can_preempt_walking(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())
        bus.publish(EventType.PET_WALK_REQUESTED)

        bus.publish(EventType.PET_SLEEP_REQUESTED)

        self.assertEqual(controller.animation_state, AnimationState.SLEEPING)

    def test_dragging_wakes_sleeping_pet(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())

        bus.publish(EventType.PET_SLEEP_REQUESTED)
        bus.publish(EventType.PET_DRAG_STARTED)

        self.assertEqual(controller.animation_state, AnimationState.DRAGGING)

    def test_walk_request_uses_legacy_instant_wake_without_staged_assets(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine(AnimationState.SLEEPING))

        bus.publish(EventType.PET_WALK_REQUESTED)

        self.assertEqual(controller.animation_state, AnimationState.WALKING)

    def test_staged_wake_waits_for_sequence_completion(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())
        controller.set_staged_sleep_enabled(True)
        bus.publish(EventType.PET_SLEEP_REQUESTED)

        bus.publish(EventType.PET_WAKE_REQUESTED)

        self.assertEqual(controller.animation_state, AnimationState.WAKING)
        bus.publish(
            EventType.ANIMATION_SEQUENCE_COMPLETED,
            {"sequence_id": AnimationSequenceId.WAKE.value},
        )
        self.assertEqual(controller.animation_state, AnimationState.IDLE)

    def test_staged_wake_queues_walk_until_completion(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())
        controller.set_staged_sleep_enabled(True)
        bus.publish(EventType.PET_SLEEP_REQUESTED)

        bus.publish(EventType.PET_WALK_REQUESTED)

        self.assertEqual(controller.animation_state, AnimationState.WAKING)
        bus.publish(
            EventType.ANIMATION_SEQUENCE_COMPLETED,
            {"sequence_id": AnimationSequenceId.WAKE.value},
        )
        self.assertEqual(controller.animation_state, AnimationState.WALKING)

    def test_click_release_wakes_to_idle_after_staged_sequence(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())
        controller.set_staged_sleep_enabled(True)
        bus.publish(EventType.PET_SLEEP_REQUESTED)

        bus.publish(EventType.PET_DRAG_STARTED)
        bus.publish(EventType.PET_DRAG_ENDED)

        self.assertEqual(controller.animation_state, AnimationState.WAKING)
        bus.publish(
            EventType.ANIMATION_SEQUENCE_COMPLETED,
            {"sequence_id": AnimationSequenceId.WAKE.value},
        )
        self.assertEqual(controller.animation_state, AnimationState.IDLE)

    def test_voice_interaction_wakes_even_without_autonomous_session(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())
        controller.set_staged_sleep_enabled(True)
        bus.publish(EventType.PET_SLEEP_REQUESTED)

        bus.publish(
            EventType.VOICE_STATE_CHANGED,
            {"state": VoiceState.LISTENING.value},
        )

        self.assertEqual(controller.animation_state, AnimationState.WAKING)

    def test_care_interaction_wakes_even_without_autonomous_session(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())
        controller.set_staged_sleep_enabled(True)
        bus.publish(EventType.PET_SLEEP_REQUESTED)

        bus.publish(EventType.PET_CARE_OPEN_REQUESTED)

        self.assertEqual(controller.animation_state, AnimationState.WAKING)


if __name__ == "__main__":
    unittest.main()
