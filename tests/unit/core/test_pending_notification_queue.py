"""Tests for bounded pending-notification aggregation."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.core.notifications import (
    NotificationChannelDecision,
    PendingNotificationQueue,
)
from project_akiha.core.notifications.pending import PendingNotification


class PendingNotificationQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)

    def test_busy_surface_retains_then_aggregates_compatible_notices(self) -> None:
        queue = PendingNotificationQueue()
        queue.enqueue(_pending(self.now, "one"))
        queue.enqueue(_pending(self.now, "two"))

        self.assertEqual(
            queue.drain_ready(
                now=self.now,
                presentation_busy=True,
                expiry_seconds=300,
            ),
            (),
        )
        batches = queue.drain_ready(
            now=self.now,
            presentation_busy=False,
            expiry_seconds=300,
        )

        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0].count, 2)

    def test_expired_notice_is_removed_without_delivery(self) -> None:
        queue = PendingNotificationQueue()
        queue.enqueue(_pending(self.now - timedelta(minutes=10), "old"))

        expired = queue.expire(now=self.now, expiry_seconds=300)
        batches = queue.drain_ready(
            now=self.now,
            presentation_busy=False,
            expiry_seconds=300,
        )

        self.assertEqual(len(expired), 1)
        self.assertEqual(batches, ())
        self.assertEqual(queue.size, 0)

    def test_full_queue_preserves_higher_priority_notice(self) -> None:
        queue = PendingNotificationQueue(maximum_size=1)
        important = _pending(self.now, "important", ExternalEventPriority.IMPORTANT)
        normal = _pending(self.now, "normal", ExternalEventPriority.NORMAL)

        self.assertTrue(queue.enqueue(important).accepted)
        result = queue.enqueue(normal)

        self.assertFalse(result.accepted)
        batches = queue.drain_ready(
            now=self.now,
            presentation_busy=False,
            expiry_seconds=300,
        )
        self.assertEqual(batches[0].notifications[0].event.external_id, "important")

    def test_full_queue_reports_evicted_lower_priority_notice(self) -> None:
        queue = PendingNotificationQueue(maximum_size=1)
        low = _pending(self.now, "low", ExternalEventPriority.LOW)
        critical = _pending(self.now, "critical", ExternalEventPriority.CRITICAL)

        queue.enqueue(low)
        result = queue.enqueue(critical)

        self.assertTrue(result.accepted)
        self.assertIsNotNone(result.evicted)
        assert result.evicted is not None
        self.assertEqual(result.evicted.event.external_id, "low")


def _pending(
    now: datetime,
    external_id: str,
    priority: ExternalEventPriority = ExternalEventPriority.NORMAL,
) -> PendingNotification:
    return PendingNotification(
        event=ExternalEvent(
            service=ExternalService.DISCORD,
            external_id=external_id,
            kind=ExternalEventKind.DISCORD_MENTION,
            occurred_at=now,
            sender_display="Example",
            classification=ExternalClassification.GENERAL,
            priority=priority,
        ),
        display_text="Example mentioned Akiha Bot on Discord.",
        speech_text="Notice",
        channels=NotificationChannelDecision(True, True, True),
        enqueued_at=now,
        eligible_at=now,
    )


if __name__ == "__main__":
    unittest.main()
