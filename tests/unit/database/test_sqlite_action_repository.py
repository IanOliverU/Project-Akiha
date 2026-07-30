"""Tests for assistant permission and audit SQLite persistence."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionStatus,
    PermissionDecision,
)
from project_akiha.database import SQLiteActionRepository


class SQLiteActionRepositoryTest(unittest.TestCase):
    """Verify scoped grants and sanitized audit rows."""

    def test_grant_is_idempotent_until_revoked(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")

            first = asyncio.run(
                repository.grant_permission("files.search", r"C:\Users\Akiha\Docs")
            )
            duplicate = asyncio.run(
                repository.grant_permission("files.search", r"C:\Users\Akiha\Docs")
            )
            revoked = asyncio.run(repository.revoke_permission(first.id))
            replacement = asyncio.run(
                repository.grant_permission("files.search", r"C:\Users\Akiha\Docs")
            )

        self.assertEqual(duplicate.id, first.id)
        self.assertTrue(revoked)
        self.assertNotEqual(replacement.id, first.id)

    def test_filters_active_permissions_and_revoke_is_idempotent(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            search = asyncio.run(
                repository.grant_permission("files.search", r"C:\Users\Akiha\Docs")
            )
            asyncio.run(repository.grant_permission("applications.launch", "spotify"))

            self.assertTrue(asyncio.run(repository.revoke_permission(search.id)))
            self.assertFalse(asyncio.run(repository.revoke_permission(search.id)))
            active = asyncio.run(repository.get_active_permissions())
            apps = asyncio.run(repository.get_active_permissions("applications.launch"))

        self.assertEqual(tuple(item.target for item in active), ("spotify",))
        self.assertEqual(apps, active)

    def test_atomically_sets_and_revokes_directory_capabilities(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            target = r"C:\Users\Akiha\Documents"

            search_only = asyncio.run(
                repository.set_directory_permissions(
                    target,
                    allow_search=True,
                    allow_open=False,
                )
            )
            both = asyncio.run(
                repository.set_directory_permissions(
                    target,
                    allow_search=True,
                    allow_open=True,
                )
            )
            open_only = asyncio.run(
                repository.set_directory_permissions(
                    target,
                    allow_search=False,
                    allow_open=True,
                )
            )
            revoked_count = asyncio.run(repository.revoke_directory_permissions(target))
            active = asyncio.run(repository.get_active_permissions())

        self.assertEqual(
            tuple(item.capability for item in search_only),
            ("files.search",),
        )
        self.assertEqual(
            {item.capability for item in both},
            {"files.search", "files.open"},
        )
        self.assertEqual(
            tuple(item.capability for item in open_only),
            ("files.open",),
        )
        self.assertEqual(revoked_count, 1)
        self.assertEqual(active, ())

    def test_directory_permission_update_rolls_back_as_one_transaction(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "akiha.sqlite3"
            repository = SQLiteActionRepository(database_path)
            connection = sqlite3.connect(database_path)
            try:
                connection.executescript("""
                    CREATE TRIGGER reject_open_permission
                    BEFORE INSERT ON assistant_action_permissions
                    WHEN NEW.capability = 'files.open'
                    BEGIN
                        SELECT RAISE(ABORT, 'blocked for transaction test');
                    END;
                    """)
                connection.commit()
            finally:
                connection.close()

            with self.assertRaises(sqlite3.IntegrityError):
                asyncio.run(
                    repository.set_directory_permissions(
                        r"C:\Users\Akiha\Documents",
                        allow_search=True,
                        allow_open=True,
                    )
                )
            active = asyncio.run(repository.get_active_permissions())

        self.assertEqual(active, ())

    def test_records_and_loads_sanitized_action_audit(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")

            recorded = asyncio.run(
                repository.record_action_audit(
                    correlation_id="request-1",
                    action_id="applications.launch",
                    source="chat",
                    normalized_target="spotify",
                    permission_decision=PermissionDecision.MISSING,
                    result_status=ActionStatus.DENIED,
                    duration_ms=4,
                    failure_category=ActionFailureCategory.PERMISSION_REQUIRED,
                )
            )
            recent = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(recent, (recorded,))
        self.assertEqual(recorded.normalized_target, "spotify")
        self.assertEqual(
            recorded.failure_category,
            ActionFailureCategory.PERMISSION_REQUIRED,
        )

    def test_clears_action_audit_history(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            asyncio.run(
                repository.record_action_audit(
                    correlation_id="request-1",
                    action_id="applications.launch",
                    source="chat",
                    normalized_target="spotify",
                    permission_decision=PermissionDecision.MISSING,
                    result_status=ActionStatus.DENIED,
                    duration_ms=4,
                    failure_category=ActionFailureCategory.PERMISSION_REQUIRED,
                )
            )

            cleared = asyncio.run(repository.clear_action_audits())
            recent = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(cleared, 1)
        self.assertEqual(recent, ())

    def test_audit_schema_has_no_request_payload_or_file_content_column(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "akiha.sqlite3"
            SQLiteActionRepository(database_path)

            connection = sqlite3.connect(database_path)
            try:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(assistant_action_audit)"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(
            columns,
            {
                "id",
                "correlation_id",
                "action_id",
                "source",
                "normalized_target",
                "permission_decision",
                "result_status",
                "duration_ms",
                "failure_category",
                "created_at",
            },
        )

    def test_rejects_invalid_repository_inputs(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")

            with self.assertRaises(ValueError):
                asyncio.run(repository.grant_permission(" ", "spotify"))
            with self.assertRaises(ValueError):
                asyncio.run(repository.revoke_permission(0))
            with self.assertRaises(ValueError):
                asyncio.run(repository.get_recent_action_audits(limit=0))


if __name__ == "__main__":
    unittest.main()
