"""Tests for pure, clock-independent pet-state rules."""

from __future__ import annotations

import unittest
from datetime import timedelta

from project_akiha.core.pet import (
    DecayMode,
    DecayStatus,
    PetDecayPolicy,
    PetNeed,
    PetProgression,
    PetState,
    PetWellbeing,
    WellbeingBand,
    collect_band_transitions,
    evaluate_elapsed_decay,
)


class PetDecayRuleTest(unittest.TestCase):
    """Verify deterministic decay, caps, floors, and threshold edges."""

    def test_applies_approved_decay_intervals(self) -> None:
        outcome = evaluate_elapsed_decay(PetState.initial(), timedelta(minutes=90))

        self.assertEqual(outcome.current_state.wellbeing.satiety, 78)
        self.assertEqual(outcome.current_state.wellbeing.energy, 79)
        self.assertEqual(outcome.current_state.wellbeing.attention, 69)
        self.assertEqual(outcome.current_state.wellbeing.affection, 50)
        self.assertEqual(outcome.current_state.progression, PetProgression())
        self.assertEqual(outcome.status, DecayStatus.APPLIED)

    def test_carries_partial_intervals_between_evaluations(self) -> None:
        first = evaluate_elapsed_decay(PetState.initial(), timedelta(minutes=20))
        second = evaluate_elapsed_decay(
            first.current_state,
            timedelta(minutes=25),
        )

        self.assertEqual(first.current_state.wellbeing.satiety, 80)
        self.assertEqual(first.current_state.decay_progress.satiety_seconds, 1200)
        self.assertEqual(second.current_state.wellbeing.satiety, 79)
        self.assertEqual(second.current_state.decay_progress.satiety_seconds, 0)
        self.assertEqual(second.current_state.decay_progress.energy_seconds, 2700)

    def test_offline_catch_up_is_capped_at_twelve_hours(self) -> None:
        outcome = evaluate_elapsed_decay(
            PetState.initial(),
            timedelta(days=2),
            mode=DecayMode.OFFLINE_CATCH_UP,
        )

        self.assertTrue(outcome.was_capped)
        self.assertEqual(outcome.requested_elapsed_seconds, 2 * 24 * 60 * 60)
        self.assertEqual(outcome.applied_elapsed_seconds, 12 * 60 * 60)
        self.assertEqual(outcome.current_state.wellbeing.satiety, 64)
        self.assertEqual(outcome.current_state.wellbeing.energy, 68)
        self.assertEqual(outcome.current_state.wellbeing.attention, 62)

    def test_runtime_elapsed_time_is_not_offline_capped(self) -> None:
        outcome = evaluate_elapsed_decay(PetState.initial(), timedelta(hours=24))

        self.assertFalse(outcome.was_capped)
        self.assertEqual(outcome.applied_elapsed_seconds, 24 * 60 * 60)
        self.assertEqual(outcome.current_state.wellbeing.satiety, 48)
        self.assertEqual(outcome.current_state.wellbeing.energy, 56)
        self.assertEqual(outcome.current_state.wellbeing.attention, 54)

    def test_clock_rollback_and_zero_elapsed_leave_state_unchanged(self) -> None:
        state = PetState.initial()
        rollback = evaluate_elapsed_decay(state, timedelta(seconds=-1))
        zero = evaluate_elapsed_decay(state, timedelta())

        self.assertIs(rollback.current_state, state)
        self.assertEqual(rollback.status, DecayStatus.CLOCK_ROLLBACK)
        self.assertEqual(rollback.applied_elapsed_seconds, 0)
        self.assertIs(zero.current_state, state)
        self.assertEqual(zero.status, DecayStatus.NO_ELAPSED_TIME)

    def test_floor_clamps_and_discards_hidden_elapsed_progress(self) -> None:
        state = PetState(
            wellbeing=PetWellbeing(satiety=1, energy=1, attention=1, affection=50)
        )
        first = evaluate_elapsed_decay(state, timedelta(hours=6))
        second = evaluate_elapsed_decay(first.current_state, timedelta(hours=6))

        self.assertEqual(first.current_state.wellbeing.satiety, 0)
        self.assertEqual(first.current_state.wellbeing.energy, 0)
        self.assertEqual(first.current_state.wellbeing.attention, 0)
        self.assertEqual(first.current_state.decay_progress.satiety_seconds, 0)
        self.assertEqual(first.band_transitions, ())
        self.assertFalse(second.wellbeing_changed)
        self.assertEqual(second.band_transitions, ())

    def test_emits_edge_transition_only_when_crossing_a_band(self) -> None:
        state = PetState(wellbeing=PetWellbeing(satiety=51))
        outcome = evaluate_elapsed_decay(state, timedelta(minutes=45))

        self.assertEqual(len(outcome.band_transitions), 1)
        transition = outcome.band_transitions[0]
        self.assertIs(transition.need, PetNeed.SATIETY)
        self.assertIs(transition.previous_band, WellbeingBand.STABLE)
        self.assertIs(transition.current_band, WellbeingBand.LOW)

    def test_large_change_reports_each_adjacent_threshold(self) -> None:
        transitions = collect_band_transitions(PetNeed.ENERGY, 80, 20)

        self.assertEqual(
            tuple(
                (transition.previous_band, transition.current_band)
                for transition in transitions
            ),
            (
                (WellbeingBand.STABLE, WellbeingBand.LOW),
                (WellbeingBand.LOW, WellbeingBand.CRITICAL),
            ),
        )

    def test_recovery_edges_are_available_for_future_care_rules(self) -> None:
        transitions = collect_band_transitions(PetNeed.ATTENTION, 20, 60)

        self.assertEqual(
            tuple(
                (transition.previous_band, transition.current_band)
                for transition in transitions
            ),
            (
                (WellbeingBand.CRITICAL, WellbeingBand.LOW),
                (WellbeingBand.LOW, WellbeingBand.STABLE),
            ),
        )

    def test_evaluation_is_deterministic_for_the_same_inputs(self) -> None:
        state = PetState.initial()
        elapsed = timedelta(minutes=137)

        self.assertEqual(
            evaluate_elapsed_decay(state, elapsed),
            evaluate_elapsed_decay(state, elapsed),
        )

    def test_rule_rejects_text_and_untyped_policy_inputs(self) -> None:
        state = PetState.initial()
        invalid_calls = (
            lambda: evaluate_elapsed_decay(state, "45 minutes"),  # type: ignore[arg-type]
            lambda: evaluate_elapsed_decay(
                state,
                timedelta(minutes=45),
                mode="offline_catch_up",  # type: ignore[arg-type]
            ),
            lambda: evaluate_elapsed_decay(
                state,
                timedelta(minutes=45),
                policy={"satiety_interval_seconds": 1},  # type: ignore[arg-type]
            ),
        )

        for call in invalid_calls:
            with self.subTest(call=call):
                with self.assertRaises(TypeError):
                    call()

    def test_custom_typed_policy_can_accelerate_deterministic_tests(self) -> None:
        policy = PetDecayPolicy(
            satiety_interval_seconds=10,
            energy_interval_seconds=20,
            attention_interval_seconds=30,
            offline_cap_seconds=60,
        )

        outcome = evaluate_elapsed_decay(
            PetState.initial(),
            timedelta(seconds=30),
            policy=policy,
        )

        self.assertEqual(outcome.current_state.wellbeing.satiety, 77)
        self.assertEqual(outcome.current_state.wellbeing.energy, 79)
        self.assertEqual(outcome.current_state.wellbeing.attention, 69)


if __name__ == "__main__":
    unittest.main()
