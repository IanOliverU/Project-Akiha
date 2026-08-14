"""Tests for app-level proactive suggestion publishing."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.app.proactive_controller import ProactiveController
from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ProactiveSuggestionEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import PetBandTransition, PetNeed, WellbeingBand


class ProactiveControllerTest(unittest.TestCase):
    """Verify proactive suggestions are emitted through the app event bus."""

    def test_idle_state_change_publishes_suggestion_when_allowed(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        ProactiveController(bus, _engine(proactive_enabled=True))

        bus.publish(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            _activity(ActivityState.IDLE).payload,
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].payload["kind"], "idle_check_in")
        self.assertEqual(suggestions[0].payload["activity_state"], "idle")

    def test_active_state_change_does_not_publish_suggestion(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        ProactiveController(bus, _engine(proactive_enabled=True))

        bus.publish(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            _activity(ActivityState.ACTIVE).payload,
        )

        self.assertEqual(suggestions, [])

    def test_invalid_activity_payload_is_ignored(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        ProactiveController(bus, _engine(proactive_enabled=True))

        bus.publish(EventType.USER_ACTIVITY_STATE_CHANGED, {"state": "idle"})

        self.assertEqual(suggestions, [])

    def test_direct_snapshot_evaluation_publishes_suggestion(self) -> None:
        bus = EventBus()
        suggestions: list[Event] = []
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        controller = ProactiveController(bus, _engine(proactive_enabled=True))

        suggestion = controller.evaluate_snapshot(
            _activity(ActivityState.IDLE).snapshot,
            now=_now(),
        )

        self.assertIsNotNone(suggestion)
        self.assertEqual(len(suggestions), 1)

    def test_pet_transitions_publish_typed_edges_and_one_priority_suggestion(
        self,
    ) -> None:
        bus = EventBus()
        edges: list[Event] = []
        suggestions: list[Event] = []
        bus.subscribe(EventType.PET_NEED_BAND_CHANGED, edges.append)
        bus.subscribe(EventType.PROACTIVE_SUGGESTION_READY, suggestions.append)
        controller = ProactiveController(bus, _engine(proactive_enabled=True))
        transitions = (
            _transition(
                PetNeed.ATTENTION,
                WellbeingBand.STABLE,
                WellbeingBand.LOW,
            ),
            _transition(
                PetNeed.ENERGY,
                WellbeingBand.LOW,
                WellbeingBand.CRITICAL,
            ),
        )

        suggestion = controller.evaluate_pet_transitions(
            transitions,
            _activity(ActivityState.ACTIVE).snapshot,
            now=_now(),
        )

        self.assertIsNotNone(suggestion)
        self.assertEqual(len(edges), 2)
        self.assertEqual([event.payload["selected"] for event in edges], [False, True])
        self.assertEqual(suggestions[0].payload["kind"], "pet_need_energy_critical")

    def test_pet_transition_input_must_be_typed(self) -> None:
        controller = ProactiveController(EventBus(), _engine(proactive_enabled=True))

        with self.assertRaises(TypeError):
            controller.evaluate_pet_transitions(  # type: ignore[arg-type]
                ("pet.need.satiety.low",),
                _activity(ActivityState.ACTIVE).snapshot,
            )


def _engine(proactive_enabled: bool) -> ProactiveSuggestionEngine:
    return ProactiveSuggestionEngine(
        NotificationPolicy(BehaviorConfig(proactive_enabled=proactive_enabled))
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


class _ActivityFixture:
    def __init__(self, state: ActivityState) -> None:
        self.snapshot = ActivitySnapshot(
            state=state,
            idle_seconds=300,
            last_activity_at=_now() - timedelta(seconds=300),
            source="test",
        )

    @property
    def payload(self) -> dict[str, object]:
        return {
            "state": self.snapshot.state.value,
            "idle_seconds": self.snapshot.idle_seconds,
            "last_activity_at": self.snapshot.last_activity_at.isoformat(),
            "source": self.snapshot.source,
        }


def _activity(state: ActivityState) -> _ActivityFixture:
    return _ActivityFixture(state)


def _transition(
    need: PetNeed,
    previous_band: WellbeingBand,
    current_band: WellbeingBand,
) -> PetBandTransition:
    return PetBandTransition(
        need=need,
        previous_band=previous_band,
        current_band=current_band,
    )


if __name__ == "__main__":
    unittest.main()
