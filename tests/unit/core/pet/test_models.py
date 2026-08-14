"""Tests for typed pet-state models and invariants."""

from __future__ import annotations

import unittest
from dataclasses import fields
from datetime import UTC, datetime
from uuid import uuid4

from project_akiha.core.pet import (
    CareAction,
    PetBandTransition,
    PetDecayPolicy,
    PetDecayProgress,
    PetInteractionEvent,
    PetInteractionKind,
    PetNeed,
    PetProgression,
    PetState,
    PetWellbeing,
    WellbeingBand,
    wellbeing_band,
)


class PetStateModelTest(unittest.TestCase):
    """Verify the approved Phase 9B domain contract."""

    def test_initial_state_uses_gentle_profile_values(self) -> None:
        state = PetState.initial()

        self.assertEqual(state.wellbeing.satiety, 80)
        self.assertEqual(state.wellbeing.energy, 80)
        self.assertEqual(state.wellbeing.attention, 70)
        self.assertEqual(state.wellbeing.affection, 50)
        self.assertEqual(state.progression, PetProgression(xp=0, level=1, currency=0))
        self.assertEqual(state.decay_progress, PetDecayProgress())

    def test_wellbeing_accepts_inclusive_bounds(self) -> None:
        wellbeing = PetWellbeing(satiety=0, energy=100, attention=25, affection=50)

        self.assertEqual(wellbeing.band_for(PetNeed.SATIETY), WellbeingBand.CRITICAL)
        self.assertEqual(wellbeing.band_for(PetNeed.ENERGY), WellbeingBand.STABLE)

    def test_wellbeing_rejects_out_of_range_or_boolean_values(self) -> None:
        for value in (-1, 101, True):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    PetWellbeing(satiety=value)

    def test_progression_and_decay_progress_reject_invalid_values(self) -> None:
        invalid_factories = (
            lambda: PetProgression(xp=-1),
            lambda: PetProgression(level=0),
            lambda: PetProgression(currency=True),
            lambda: PetDecayProgress(attention_seconds=-1),
            lambda: PetDecayProgress(energy_seconds=False),
        )

        for factory in invalid_factories:
            with self.subTest(factory=factory):
                with self.assertRaises((TypeError, ValueError)):
                    factory()

    def test_state_requires_typed_nested_values(self) -> None:
        with self.assertRaises(TypeError):
            PetState(wellbeing={"satiety": 80})  # type: ignore[arg-type]

    def test_bands_use_approved_edge_inclusive_ranges(self) -> None:
        expected = {
            0: WellbeingBand.CRITICAL,
            25: WellbeingBand.CRITICAL,
            26: WellbeingBand.LOW,
            50: WellbeingBand.LOW,
            51: WellbeingBand.STABLE,
            100: WellbeingBand.STABLE,
        }

        self.assertEqual(
            {value: wellbeing_band(value) for value in expected},
            expected,
        )

    def test_interaction_event_is_structured_and_language_neutral(self) -> None:
        event = PetInteractionEvent(
            event_id=uuid4(),
            kind=PetInteractionKind.CONVERSATION_COMPLETED,
            occurred_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        )

        self.assertIs(event.kind, PetInteractionKind.CONVERSATION_COMPLETED)
        self.assertEqual(
            {field.name for field in fields(PetInteractionEvent)},
            {"event_id", "kind", "occurred_at"},
        )

    def test_interaction_event_rejects_text_kind_and_naive_time(self) -> None:
        with self.assertRaises(TypeError):
            PetInteractionEvent(
                event_id=uuid4(),
                kind="conversation_completed",  # type: ignore[arg-type]
                occurred_at=datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
            )
        with self.assertRaises(ValueError):
            PetInteractionEvent(
                event_id=uuid4(),
                kind=PetInteractionKind.CONVERSATION_COMPLETED,
                occurred_at=datetime(2026, 8, 14, 12, 0),
            )

    def test_care_actions_are_a_closed_typed_set(self) -> None:
        self.assertEqual(
            tuple(CareAction),
            (CareAction.FEED, CareAction.REST, CareAction.SPEND_TIME),
        )

    def test_band_transition_requires_one_adjacent_edge(self) -> None:
        with self.assertRaises(ValueError):
            PetBandTransition(
                need=PetNeed.SATIETY,
                previous_band=WellbeingBand.STABLE,
                current_band=WellbeingBand.CRITICAL,
            )

    def test_decay_policy_rejects_nonpositive_or_boolean_intervals(self) -> None:
        for value in (0, -1, True):
            with self.subTest(value=value):
                with self.assertRaises((TypeError, ValueError)):
                    PetDecayPolicy(satiety_interval_seconds=value)


if __name__ == "__main__":
    unittest.main()
