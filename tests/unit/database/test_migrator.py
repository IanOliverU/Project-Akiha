"""Tests for SQLite schema migrations."""

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.database import DatabaseMigrator


class DatabaseMigratorTest(unittest.TestCase):
    """Verify migration application and version tracking."""

    def test_applies_migrations_and_tracks_schema_version(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "akiha.sqlite3"
            migrator = DatabaseMigrator(database_path)

            migrator.apply_pending()
            migrator.apply_pending()

            connection = sqlite3.connect(database_path)
            try:
                table_names = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                versions = connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                ).fetchall()
                conversation_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(conversations)")
                }
                memory_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(memories)")
                }
            finally:
                connection.close()

        self.assertIn("schema_version", table_names)
        self.assertIn("conversations", table_names)
        self.assertIn("messages", table_names)
        self.assertIn("memories", table_names)
        self.assertIn("behavior_events", table_names)
        self.assertIn("summary", conversation_columns)
        self.assertIn("archived_at", memory_columns)
        self.assertIn("embedding_json", memory_columns)
        self.assertEqual(versions, [(1,), (2,), (3,), (4,), (5,), (6,)])


if __name__ == "__main__":
    unittest.main()
