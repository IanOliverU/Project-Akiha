"""Tests for pure pet progression and anti-farming rules."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from project_akiha.core.pet import (
    CareAction,
    PetInteractionEvent,
    PetInteractionKind,
    PetProgression,
    PetRewardDecision,
    PetRewardGrant,
    PetRewardKind,
    evaluate_care_reward,
    evaluate_interaction_reward,
    level_for_xp,
    xp_required_for_level,
)


class PetProgressionRuleTest(unittest.TestCase):
    """Verify level thresholds, cooldowns, rolling caps, and deduplication."""

    def setUp(self) -> None:
        self._now = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

    def test_level_curve_uses_cumulative_triangular_thresholds(self) -> None:
        expected = {
            0: 1,
            24: 1,
            25: 2,
            74: 2,
            75: 3,
            149: 3,
            150: 4,
            249: 4,
            250: 5,
        }

        for xp, level in expected.items():
            with self.subTest(xp=xp):
                self.assertEqual(level_for_xp(xp), level)

        self.assertEqual(
            tuple(xp_required_for_level(level) for level in range(1, 6)),
            (0, 25, 75, 150, 250),
        )

    def test_eligible_care_grants_xp_currency_and_derives_level(self) -> None:
        progression = PetProgression(xp=20, level=1, currency=3)

        outcome = evaluate_care_reward(
            progression,
            CareAction.FEED,
            care_changed=True,
            recent_grants=(),
            granted_at=self._now,
        )

        self.assertTrue(outcome.granted)
        self.assertEqual(outcome.current_progression.xp, 25)
        self.assertEqual(outcome.current_progression.level, 2)
        self.assertEqual(outcome.current_progression.currency, 5)
        self.assertEqual(outcome.grant.xp_awarded, 5)
        self.assertEqual(outcome.grant.currency_awarded, 2)

    def test_care_cooldown_is_per_action_kind(self) -> None:
        prior_feed = _care_grant(
            PetRewardKind.CARE_FEED,
            self._now - timedelta(minutes=10),
        )

        blocked = evaluate_care_reward(
            PetProgression(),
            CareAction.FEED,
            care_changed=True,
            recent_grants=(prior_feed,),
            granted_at=self._now,
        )
        allowed = evaluate_care_reward(
            PetProgression(),
            CareAction.REST,
            care_changed=True,
            recent_grants=(prior_feed,),
            granted_at=self._now,
        )

        self.assertIs(blocked.decision, PetRewardDecision.COOLDOWN)
        self.assertTrue(allowed.granted)

    def test_care_is_eligible_exactly_at_cooldown_boundary(self) -> None:
        prior = _care_grant(
            PetRewardKind.CARE_FEED,
            self._now - timedelta(minutes=30),
        )

        outcome = evaluate_care_reward(
            PetProgression(),
            CareAction.FEED,
            care_changed=True,
            recent_grants=(prior,),
            granted_at=self._now,
        )

        self.assertTrue(outcome.granted)

    def test_care_daily_cap_counts_all_care_reward_kinds(self) -> None:
        kinds = (
            PetRewardKind.CARE_FEED,
            PetRewardKind.CARE_REST,
            PetRewardKind.CARE_SPEND_TIME,
        )
        grants = tuple(
            _care_grant(
                kinds[index % len(kinds)],
                self._now - timedelta(hours=index + 1),
            )
            for index in range(12)
        )

        outcome = evaluate_care_reward(
            PetProgression(),
            CareAction.FEED,
            care_changed=True,
            recent_grants=grants,
            granted_at=self._now,
        )

        self.assertIs(outcome.decision, PetRewardDecision.DAILY_CAP)

    def test_unchanged_care_never_grants_a_reward(self) -> None:
        outcome = evaluate_care_reward(
            PetProgression(),
            CareAction.FEED,
            care_changed=False,
            recent_grants=(),
            granted_at=self._now,
        )

        self.assertIs(outcome.decision, PetRewardDecision.NO_STATE_CHANGE)
        self.assertEqual(outcome.current_progression, PetProgression())

    def test_conversation_reward_uses_cooldown_and_unique_event(self) -> None:
        event = _conversation_event(self._now)
        first = evaluate_interaction_reward(
            PetProgression(),
            event,
            event_already_rewarded=False,
            recent_grants=(),
            granted_at=self._now,
        )
        duplicate = evaluate_interaction_reward(
            first.current_progression,
            event,
            event_already_rewarded=True,
            recent_grants=(first.grant,),
            granted_at=self._now,
        )
        second_event = evaluate_interaction_reward(
            first.current_progression,
            _conversation_event(self._now),
            event_already_rewarded=False,
            recent_grants=(first.grant,),
            granted_at=self._now,
        )

        self.assertEqual(first.current_progression.xp, 1)
        self.assertEqual(first.current_progression.currency, 0)
        self.assertIs(duplicate.decision, PetRewardDecision.DUPLICATE_EVENT)
        self.assertIs(second_event.decision, PetRewardDecision.COOLDOWN)

    def test_conversation_daily_cap_is_rolling_and_independent(self) -> None:
        grants = tuple(
            _conversation_grant(
                self._now - timedelta(hours=index + 1),
            )
            for index in range(12)
        )

        outcome = evaluate_interaction_reward(
            PetProgression(),
            _conversation_event(self._now),
            event_already_rewarded=False,
            recent_grants=grants,
            granted_at=self._now,
        )

        self.assertIs(outcome.decision, PetRewardDecision.DAILY_CAP)

    def test_future_grants_do_not_bypass_limits_after_clock_rollback(self) -> None:
        future = _care_grant(
            PetRewardKind.CARE_FEED,
            self._now + timedelta(minutes=5),
        )

        outcome = evaluate_care_reward(
            PetProgression(),
            CareAction.FEED,
            care_changed=True,
            recent_grants=(future,),
            granted_at=self._now,
        )

        self.assertIs(outcome.decision, PetRewardDecision.COOLDOWN)

    def test_rules_reject_untyped_values(self) -> None:
        with self.assertRaises(TypeError):
            level_for_xp(True)
        with self.assertRaises(ValueError):
            xp_required_for_level(0)
        with self.assertRaises(TypeError):
            evaluate_care_reward(
                PetProgression(),
                "feed",  # type: ignore[arg-type]
                care_changed=True,
                recent_grants=(),
                granted_at=self._now,
            )
        with self.assertRaises(TypeError):
            evaluate_interaction_reward(
                PetProgression(),
                "conversation",  # type: ignore[arg-type]
                event_already_rewarded=False,
                recent_grants=(),
                granted_at=self._now,
            )

    def test_reward_grants_reject_unapproved_amounts(self) -> None:
        with self.assertRaises(ValueError):
            PetRewardGrant(
                kind=PetRewardKind.CARE_FEED,
                event_id=None,
                xp_awarded=50,
                currency_awarded=20,
                granted_at=self._now,
            )
        with self.assertRaises(ValueError):
            PetRewardGrant(
                kind=PetRewardKind.CONVERSATION_COMPLETED,
                event_id=uuid4(),
                xp_awarded=5,
                currency_awarded=0,
                granted_at=self._now,
            )


def _care_grant(kind: PetRewardKind, granted_at: datetime) -> PetRewardGrant:
    return PetRewardGrant(
        kind=kind,
        event_id=None,
        xp_awarded=5,
        currency_awarded=2,
        granted_at=granted_at,
    )


def _conversation_grant(granted_at: datetime) -> PetRewardGrant:
    return PetRewardGrant(
        kind=PetRewardKind.CONVERSATION_COMPLETED,
        event_id=uuid4(),
        xp_awarded=1,
        currency_awarded=0,
        granted_at=granted_at,
    )


def _conversation_event(occurred_at: datetime) -> PetInteractionEvent:
    return PetInteractionEvent(
        event_id=uuid4(),
        kind=PetInteractionKind.CONVERSATION_COMPLETED,
        occurred_at=occurred_at,
    )


if __name__ == "__main__":
    unittest.main()
