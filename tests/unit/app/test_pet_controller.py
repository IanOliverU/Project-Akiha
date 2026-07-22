"""Tests for the Phase 1 pet controller."""

from __future__ import annotations

import unittest

from project_akiha.app.pet_controller import PetController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.animation import AnimationState, AnimationStateMachine


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

    def test_sleep_and_wake_events_change_animation_state(self) -> None:
        bus = EventBus()
        controller = PetController(bus, AnimationStateMachine())

        bus.publish(EventType.PET_SLEEP_REQUESTED)
        self.assertEqual(controller.animation_state, AnimationState.SLEEPING)

        bus.publish(EventType.PET_WAKE_REQUESTED)
        self.assertEqual(controller.animation_state, AnimationState.IDLE)

    def test_invalid_transition_publishes_error(self) -> None:
        bus = EventBus()
        errors: list[Event] = []
        bus.subscribe(EventType.ERROR_OCCURRED, errors.append)
        controller = PetController(bus, AnimationStateMachine(AnimationState.SLEEPING))

        bus.publish(EventType.PET_DRAG_STARTED)

        self.assertEqual(controller.animation_state, AnimationState.SLEEPING)
        self.assertEqual(errors[-1].event_type, EventType.ERROR_OCCURRED)


if __name__ == "__main__":
    unittest.main()
