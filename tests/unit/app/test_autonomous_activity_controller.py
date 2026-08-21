"""Tests for preemptible autonomous pet activity orchestration."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from project_akiha.app.autonomous_activity_controller import (
    AutonomousActivityController,
)
from project_akiha.app.pet_controller import PetController
from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import PetState
from project_akiha.core.pet_activity import load_pet_activity_manifest
from project_akiha.core.state.animation import AnimationState, AnimationStateMachine


class AutonomousActivityControllerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.bus = EventBus()
        self.pet = PetController(self.bus, AnimationStateMachine())
        self.events: list[Event] = []
        for event_type in (
            EventType.PET_ACTIVITY_STARTED,
            EventType.PET_ACTIVITY_COMPLETED,
            EventType.PET_ACTIVITY_CANCELLED,
        ):
            self.bus.subscribe(event_type, self.events.append)
        self.controller = AutonomousActivityController(
            self.bus,
            load_pet_activity_manifest(Path("assets/animations/activities.toml")),
            initial_user_activity=ActivityState.IDLE,
            initial_mood=CompanionMood.WAITING,
            initial_pet_state=PetState.initial(),
        )

    def test_wander_starts_completes_and_returns_to_idle(self) -> None:
        self.controller.tick(_now())

        self.assertEqual(self.pet.animation_state, AnimationState.WALKING)
        self.assertEqual(self.events[-1].event_type, EventType.PET_ACTIVITY_STARTED)

        self.controller.tick(_now() + timedelta(seconds=20))

        self.assertEqual(self.pet.animation_state, AnimationState.IDLE)
        self.assertIsNone(self.controller.active_session)
        self.assertEqual(self.events[-1].event_type, EventType.PET_ACTIVITY_COMPLETED)

    def test_voice_preempts_wander_and_restores_idle(self) -> None:
        self.controller.tick(_now())

        self.bus.publish(EventType.VOICE_STATE_CHANGED, {"state": "listening"})

        self.assertEqual(self.pet.animation_state, AnimationState.IDLE)
        self.assertEqual(self.events[-1].payload["reason"], "voice_activity")

    def test_drag_preempts_without_overriding_drag_animation(self) -> None:
        self.controller.tick(_now())

        self.bus.publish(EventType.PET_DRAG_STARTED)

        self.assertEqual(self.pet.animation_state, AnimationState.DRAGGING)
        self.assertEqual(self.events[-1].payload["reason"], "drag_started")

    def test_direct_sleep_preempts_autonomous_walking(self) -> None:
        self.controller.tick(_now())

        self.bus.publish(EventType.PET_SLEEP_REQUESTED)

        self.assertEqual(self.pet.animation_state, AnimationState.SLEEPING)
        self.assertEqual(self.events[-1].payload["reason"], "direct_control")

    def test_user_activity_cancels_active_activity(self) -> None:
        self.controller.tick(_now())

        self.bus.publish(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            {
                "state": "active",
                "idle_seconds": 0,
                "last_activity_at": _now().isoformat(),
                "source": "chat_message",
            },
        )

        self.assertEqual(self.pet.animation_state, AnimationState.IDLE)
        self.assertEqual(self.events[-1].payload["reason"], "context_changed")

    def test_disabled_controller_never_starts_activity(self) -> None:
        self.controller.set_enabled(False, _now())

        self.controller.tick(_now())

        self.assertIsNone(self.controller.active_session)
        self.assertEqual(self.pet.animation_state, AnimationState.IDLE)


def _now() -> datetime:
    return datetime(2026, 8, 22, 4, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
