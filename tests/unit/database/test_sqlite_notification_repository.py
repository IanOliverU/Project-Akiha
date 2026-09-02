"""Tests for the privacy-safe Notification Center repository."""

from __future__ import annotations

import sqlite3
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.integrations import (
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.core.notifications import (
    SanitizedNotification,
)
from project_akiha.database.sqlite_notification_repository import (
    SQLiteNotificationRepository,
)


class SQLiteNotificationRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.database_path = Path(self.temporary.name) / "akiha.sqlite3"
        self.repository = SQLiteNotificationRepository(self.database_path)
        self.now = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_add_list_mark_read_and_clear(self) -> None:
        record_id = self.repository.add(_notification(self.now))

        records = self.repository.list_recent()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].id, record_id)
        self.assertEqual(records[0].display_text, "New email from Example.")
        self.assertIsNone(records[0].read_at)
        self.assertEqual(
            self.repository.mark_read((record_id,), read_at=self.now),
            1,
        )
        self.assertEqual(self.repository.list_recent(unread_only=True), ())
        self.assertEqual(self.repository.clear(), 1)

    def test_schema_has_no_raw_provider_or_credential_columns(self) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(notification_inbox)")
            }
        finally:
            connection.close()

        self.assertFalse(
            columns
            & {
                "external_id",
                "subject",
                "body",
                "payload",
                "token",
                "credential",
                "attachment",
            }
        )

    def test_prune_applies_age_and_count_bounds(self) -> None:
        for offset in range(4):
            self.repository.add(_notification(self.now - timedelta(days=offset)))

        removed = self.repository.prune(
            maximum_records=2,
            older_than=self.now - timedelta(days=30),
        )

        self.assertEqual(removed, 2)
        self.assertEqual(len(self.repository.list_recent()), 2)


def _notification(now: datetime) -> SanitizedNotification:
    return SanitizedNotification(
        service=ExternalService.GMAIL,
        event_kind=ExternalEventKind.GMAIL_NEW_MESSAGE,
        priority=ExternalEventPriority.NORMAL,
        display_text="New email from Example.",
        occurred_at=now,
        created_at=now,
    )


if __name__ == "__main__":
    unittest.main()
