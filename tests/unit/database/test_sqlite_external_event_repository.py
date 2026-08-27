"""Tests for privacy-minimal external integration persistence."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalNotificationStatus,
    ExternalService,
)
from project_akiha.database import SQLiteExternalEventRepository


class SQLiteExternalEventRepositoryTest(unittest.TestCase):
    """Verify receipts and cursors retain no communication content."""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "akiha.sqlite3"
        self.repository = SQLiteExternalEventRepository(self.database_path)
        self.now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_claim_event_is_atomic_and_deduplicates(self) -> None:
        event = _event()

        self.assertTrue(self.repository.claim_event(event, received_at=self.now))
        self.assertFalse(self.repository.claim_event(event, received_at=self.now))

    def test_receipt_does_not_persist_external_text_or_identifier(self) -> None:
        event = _event()
        self.repository.claim_event(event, received_at=self.now)

        connection = sqlite3.connect(self.database_path)
        try:
            columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(external_event_receipts)"
                )
            }
            database_text = " ".join(
                str(value)
                for row in connection.execute("SELECT * FROM external_event_receipts")
                for value in row
                if value is not None
            )
        finally:
            connection.close()

        self.assertNotIn("sender", columns)
        self.assertNotIn("subject", columns)
        self.assertNotIn("body", columns)
        self.assertNotIn("payload", columns)
        self.assertNotIn(event.external_id, database_text)
        self.assertNotIn(event.sender_display or "", database_text)
        self.assertNotIn(event.subject or "", database_text)

    def test_updates_notification_status(self) -> None:
        event = _event()
        self.repository.claim_event(event, received_at=self.now)

        self.repository.set_notification_status(
            event,
            ExternalNotificationStatus.DELIVERED,
            notified_at=self.now,
        )

        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT notification_status, notified_at "
                "FROM external_event_receipts"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row, ("delivered", "2026-08-27T12:00:00+00:00"))

    def test_cursor_round_trip_hashes_account_key(self) -> None:
        account_key = "ian@example.com"
        self.repository.save_sync_cursor(
            ExternalService.GMAIL,
            account_key,
            "history-123",
            synchronized_at=self.now,
        )

        self.assertEqual(
            self.repository.load_sync_cursor(ExternalService.GMAIL, account_key),
            "history-123",
        )
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(
                "SELECT account_key_hash, cursor FROM integration_sync_state"
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertNotEqual(row[0], account_key)
        self.assertEqual(len(row[0]), 64)
        self.assertEqual(row[1], "history-123")

    def test_cursor_update_replaces_previous_value(self) -> None:
        for cursor in ("history-123", "history-456"):
            self.repository.save_sync_cursor(
                ExternalService.GMAIL,
                "ian@example.com",
                cursor,
                synchronized_at=self.now,
            )

        self.assertEqual(
            self.repository.load_sync_cursor(
                ExternalService.GMAIL,
                "ian@example.com",
            ),
            "history-456",
        )

    def test_prunes_old_receipts_and_clear_removes_only_selected_service(self) -> None:
        old_event = _event()
        discord_event = ExternalEvent(
            service=ExternalService.DISCORD,
            external_id="discord-message-1",
            kind=ExternalEventKind.DISCORD_MENTION,
            occurred_at=self.now,
            classification=ExternalClassification.GENERAL,
            priority=ExternalEventPriority.IMPORTANT,
        )
        self.repository.claim_event(
            old_event,
            received_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.repository.claim_event(discord_event, received_at=self.now)

        removed = self.repository.prune_receipts(
            older_than=datetime(2026, 8, 1, tzinfo=UTC)
        )
        self.repository.clear_service_data(ExternalService.DISCORD)

        self.assertEqual(removed, 1)
        connection = sqlite3.connect(self.database_path)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM external_event_receipts"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 0)


def _event() -> ExternalEvent:
    return ExternalEvent(
        service=ExternalService.GMAIL,
        external_id="private-message-id-123",
        kind=ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
        occurred_at=datetime(2026, 8, 27, 11, 59, tzinfo=UTC),
        sender_display="Private Recruiter",
        subject="Private interview invitation",
        context_label="Inbox",
        classification=ExternalClassification.INTERVIEW,
        priority=ExternalEventPriority.IMPORTANT,
    )


if __name__ == "__main__":
    unittest.main()
