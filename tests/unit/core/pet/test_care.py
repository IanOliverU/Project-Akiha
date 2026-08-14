"""Tests for pure, typed pet care-action rules."""

from __future__ import annotations

import unittest

from project_akiha.core.pet import (
    CareAction,
    PetDecayProgress,
    PetNeed,
    PetProgression,
    PetState,
    PetWellbeing,
    WellbeingBand,
    apply_care_action,
)


class PetCareRuleTest(unittest.TestCase):
    """Verify explicit recovery effects, caps, and language neutrality."""

    def test_feed_rest_and_spend_time_apply_approved_effects(self) -> None:
        state = PetState(
            wellbeing=PetWellbeing(
                satiety=40,
                energy=30,
                attention=20,
                affection=50,
            )
        )

        fed = apply_care_action(state, CareAction.FEED)
        rested = apply_care_action(state, CareAction.REST)
        together = apply_care_action(state, CareAction.SPEND_TIME)

        self.assertEqual(fed.current_state.wellbeing.satiety, 65)
        self.assertEqual(rested.current_state.wellbeing.energy, 55)
        self.assertEqual(together.current_state.wellbeing.attention, 40)
        self.assertEqual(together.current_state.wellbeing.affection, 51)

    def test_actions_clamp_at_one_hundred(self) -> None:
        state = PetState(
            wellbeing=PetWellbeing(
                satiety=90,
                energy=90,
                attention=90,
                affection=100,
            )
        )

        fed = apply_care_action(state, CareAction.FEED)
        rested = apply_care_action(state, CareAction.REST)
        together = apply_care_action(state, CareAction.SPEND_TIME)

        self.assertEqual(fed.current_state.wellbeing.satiety, 100)
        self.assertEqual(rested.current_state.wellbeing.energy, 100)
        self.assertEqual(together.current_state.wellbeing.attention, 100)
        self.assertEqual(together.current_state.wellbeing.affection, 100)

    def test_each_action_recovers_its_stat_from_the_floor(self) -> None:
        state = PetState(
            wellbeing=PetWellbeing(
                satiety=0,
                energy=0,
                attention=0,
                affection=0,
            )
        )

        self.assertEqual(
            apply_care_action(state, CareAction.FEED).current_state.wellbeing.satiety,
            25,
        )
        self.assertEqual(
            apply_care_action(state, CareAction.REST).current_state.wellbeing.energy,
            25,
        )
        together = apply_care_action(state, CareAction.SPEND_TIME)
        self.assertEqual(together.current_state.wellbeing.attention, 20)
        self.assertEqual(together.current_state.wellbeing.affection, 1)

    def test_recovery_emits_only_affected_need_threshold_edges(self) -> None:
        state = PetState(wellbeing=PetWellbeing(satiety=50, energy=20))

        outcome = apply_care_action(state, CareAction.FEED)

        self.assertEqual(len(outcome.band_transitions), 1)
        transition = outcome.band_transitions[0]
        self.assertIs(transition.need, PetNeed.SATIETY)
        self.assertIs(transition.previous_band, WellbeingBand.LOW)
        self.assertIs(transition.current_band, WellbeingBand.STABLE)

    def test_care_preserves_progression_and_decay_progress(self) -> None:
        state = PetState(
            wellbeing=PetWellbeing(satiety=20),
            progression=PetProgression(xp=30, level=2, currency=12),
            decay_progress=PetDecayProgress(
                satiety_seconds=120,
                energy_seconds=240,
                attention_seconds=360,
            ),
        )

        outcome = apply_care_action(state, CareAction.FEED)

        self.assertEqual(outcome.current_state.progression, state.progression)
        self.assertEqual(outcome.current_state.decay_progress, state.decay_progress)

    def test_fully_capped_action_is_a_true_no_op(self) -> None:
        state = PetState(
            wellbeing=PetWellbeing(
                satiety=100,
                energy=100,
                attention=100,
                affection=100,
            )
        )

        for action in CareAction:
            with self.subTest(action=action):
                outcome = apply_care_action(state, action)
                self.assertFalse(outcome.changed)
                self.assertEqual(outcome.current_state, state)
                self.assertEqual(outcome.band_transitions, ())

    def test_rule_rejects_dialogue_and_untyped_actions(self) -> None:
        with self.assertRaises(TypeError):
            apply_care_action("Akiha is hungry", CareAction.FEED)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            apply_care_action(PetState.initial(), "feed")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
