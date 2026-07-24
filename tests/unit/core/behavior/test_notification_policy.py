"""Tests for proactive notification policy decisions."""

from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    NotificationRequest,
)


class NotificationPolicyTest(unittest.TestCase):
    """Verify proactive notification guardrails."""

    def test_blocks_when_proactive_behavior_is_disabled(self) -> None:
        policy = NotificationPolicy(BehaviorConfig(proactive_enabled=False))

        decision = policy.evaluate(
            NotificationRequest(kind="check_in", message="Need a break?"),
            activity=_activity(ActivityState.IDLE),
            now=_now(),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "proactive_disabled")

    def test_allows_when_enabled_and_user_is_not_away(self) -> None:
        policy = NotificationPolicy(BehaviorConfig(proactive_enabled=True))

        decision = policy.evaluate(
            NotificationRequest(kind="check_in", message="Need a break?"),
            activity=_activity(ActivityState.IDLE),
            now=_now(),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "allowed")

    def test_blocks_during_quiet_hours_that_cross_midnight(self) -> None:
        policy = NotificationPolicy(
            BehaviorConfig(
                proactive_enabled=True,
                quiet_hours_enabled=True,
                quiet_hours_start="22:00",
                quiet_hours_end="07:00",
            )
        )

        decision = policy.evaluate(
            NotificationRequest(kind="check_in", message="Need a break?"),
            activity=_activity(ActivityState.IDLE),
            now=datetime(2026, 7, 24, 23, 30, tzinfo=UTC),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "quiet_hours")

    def test_blocks_when_user_is_away_by_default(self) -> None:
        policy = NotificationPolicy(BehaviorConfig(proactive_enabled=True))

        decision = policy.evaluate(
            NotificationRequest(kind="check_in", message="Need a break?"),
            activity=_activity(ActivityState.AWAY),
            now=_now(),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "user_away")

    def test_blocks_when_notification_cooldown_is_active(self) -> None:
        now = _now()
        policy = NotificationPolicy(
            BehaviorConfig(
                proactive_enabled=True,
                minimum_seconds_between_notifications=600,
            )
        )

        decision = policy.evaluate(
            NotificationRequest(kind="check_in", message="Need a break?"),
            activity=_activity(ActivityState.IDLE),
            now=now,
            last_notification_at=now - timedelta(seconds=599),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "cooldown")

    def test_runtime_config_update_changes_decision(self) -> None:
        policy = NotificationPolicy(BehaviorConfig(proactive_enabled=False))
        policy.update_config(replace(BehaviorConfig(), proactive_enabled=True))

        decision = policy.evaluate(
            NotificationRequest(kind="check_in", message="Need a break?"),
            activity=_activity(ActivityState.IDLE),
            now=_now(),
        )

        self.assertTrue(decision.allowed)


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _activity(state: ActivityState) -> ActivitySnapshot:
    return ActivitySnapshot(
        state=state,
        idle_seconds=300,
        last_activity_at=_now() - timedelta(seconds=300),
        source="test",
    )


if __name__ == "__main__":
    unittest.main()
