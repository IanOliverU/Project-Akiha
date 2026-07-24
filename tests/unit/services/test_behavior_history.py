"""Tests for behavior history event recording."""

from __future__ import annotations

import logging
import unittest

from project_akiha.core.behavior import BehaviorEvent
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.services.behavior_history import BehaviorHistoryRecorder


class BehaviorHistoryRecorderTest(unittest.TestCase):
    """Verify selected behavior events are persisted."""

    def test_records_proactive_suggestion_events(self) -> None:
        bus = EventBus()
        repository = _RecordingRepository()
        BehaviorHistoryRecorder(bus, repository)

        bus.publish(
            EventType.PROACTIVE_SUGGESTION_READY,
            {"kind": "idle_check_in", "message": "Need a break?"},
        )
        bus.publish(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            {"kind": "idle_check_in", "delivered": True},
        )

        self.assertEqual(
            [record.event_type for record in repository.records],
            [
                "proactive.suggestion_ready",
                "proactive.suggestion_delivered",
            ],
        )
        self.assertEqual(repository.records[0].kind, "idle_check_in")

    def test_ignores_untracked_events(self) -> None:
        bus = EventBus()
        repository = _RecordingRepository()
        BehaviorHistoryRecorder(bus, repository)

        bus.publish(EventType.MOOD_STATE_CHANGED, {"mood": "calm"})

        self.assertEqual(repository.records, ())

    def test_logs_repository_failures(self) -> None:
        bus = EventBus()
        repository = _FailingRepository()
        logger = logging.getLogger("test_behavior_history")
        BehaviorHistoryRecorder(bus, repository, logger=logger)

        with self.assertLogs(logger, level="ERROR") as captured:
            bus.publish(
                EventType.PROACTIVE_SUGGESTION_READY,
                {"kind": "idle_check_in"},
            )

        self.assertIn("Failed to record behavior event", captured.output[0])


class _RecordedCall:
    def __init__(
        self,
        event_type: str,
        kind: str | None,
        payload: dict[str, object],
    ) -> None:
        self.event_type = event_type
        self.kind = kind
        self.payload = payload


class _RecordingRepository:
    def __init__(self) -> None:
        self._records: list[_RecordedCall] = []

    @property
    def records(self) -> tuple[_RecordedCall, ...]:
        return tuple(self._records)

    async def record_event(
        self,
        event_type: str,
        payload: dict[str, object],
        kind: str | None = None,
    ) -> BehaviorEvent:
        self._records.append(_RecordedCall(event_type, kind, payload))
        return BehaviorEvent(
            id=len(self._records),
            event_type=event_type,
            kind=kind,
            payload={},
            created_at="2026-07-24T12:00:00+00:00",
        )


class _FailingRepository:
    async def record_event(
        self,
        event_type: str,
        payload: dict[str, object],
        kind: str | None = None,
    ) -> BehaviorEvent:
        del event_type, payload, kind
        raise RuntimeError("boom")


if __name__ == "__main__":
    unittest.main()
