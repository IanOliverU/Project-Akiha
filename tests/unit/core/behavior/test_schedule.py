"""Tests for scheduled check-in generation."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.config import BehaviorConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ScheduledCheckInEngine,
)


class ScheduledCheckInEngineTest(unittest.TestCase):
    """Verify scheduled check-ins are generated conservatively."""

    def test_disabled_check_ins_anchor_without_suggestion(self) -> None:
        engine = _engine(scheduled_enabled=False)

        suggestion = engine.tick(_activity(), _now())

        self.assertIsNone(suggestion)
        self.assertEqual(engine.last_check_in_at, _now())

    def test_first_enabled_tick_warms_up_without_suggestion(self) -> None:
        engine = _engine(scheduled_enabled=True)

        suggestion = engine.tick(_activity(), _now())

        self.assertIsNone(suggestion)
        self.assertEqual(engine.last_check_in_at, _now())

    def test_returns_check_in_when_interval_is_due(self) -> None:
        engine = _engine(scheduled_enabled=True, initial_time=_now())

        suggestion = engine.tick(_activity(), _now() + timedelta(seconds=3600))

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.kind, "scheduled_check_in")
        self.assertEqual(suggestion.activity_state, ActivityState.ACTIVE)
        self.assertEqual(
            engine.last_check_in_at,
            _now() + timedelta(seconds=3600),
        )

    def test_returns_no_check_in_before_interval(self) -> None:
        engine = _engine(scheduled_enabled=True, initial_time=_now())

        suggestion = engine.tick(_activity(), _now() + timedelta(seconds=3599))

        self.assertIsNone(suggestion)
        self.assertEqual(engine.last_check_in_at, _now())

    def test_respects_proactive_policy(self) -> None:
        engine = ScheduledCheckInEngine(
            NotificationPolicy(
                BehaviorConfig(
                    proactive_enabled=False,
                    scheduled_check_ins_enabled=True,
                )
            ),
            BehaviorConfig(
                proactive_enabled=False,
                scheduled_check_ins_enabled=True,
            ),
            initial_time=_now(),
        )

        suggestion = engine.tick(_activity(), _now() + timedelta(seconds=3600))

        self.assertIsNone(suggestion)

    def test_runtime_config_update_enables_future_check_ins(self) -> None:
        config = BehaviorConfig(scheduled_check_ins_enabled=False)
        policy = NotificationPolicy(config)
        engine = ScheduledCheckInEngine(
            policy,
            config,
            initial_time=_now(),
        )
        updated_config = BehaviorConfig(
            proactive_enabled=True,
            scheduled_check_ins_enabled=True,
            scheduled_check_in_interval_seconds=60,
            minimum_seconds_between_notifications=60,
        )
        policy.update_config(updated_config)
        engine.update_config(updated_config)

        suggestion = engine.tick(_activity(), _now() + timedelta(seconds=60))

        self.assertIsNotNone(suggestion)


def _engine(
    *,
    scheduled_enabled: bool,
    initial_time: datetime | None = None,
) -> ScheduledCheckInEngine:
    config = BehaviorConfig(
        proactive_enabled=True,
        scheduled_check_ins_enabled=scheduled_enabled,
        scheduled_check_in_interval_seconds=3600,
    )
    return ScheduledCheckInEngine(
        NotificationPolicy(config),
        config,
        initial_time=initial_time,
    )


def _activity() -> ActivitySnapshot:
    return ActivitySnapshot(
        state=ActivityState.ACTIVE,
        idle_seconds=0,
        last_activity_at=_now(),
        source="test",
    )


def _now() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


if __name__ == "__main__":
    unittest.main()
