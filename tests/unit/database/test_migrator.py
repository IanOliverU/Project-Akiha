"""Tests for SQLite schema migrations."""

from __future__ import annotations

import shutil
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
                message_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(messages)")
                }
            finally:
                connection.close()

        self.assertIn("schema_version", table_names)
        self.assertIn("conversations", table_names)
        self.assertIn("messages", table_names)
        self.assertIn("memories", table_names)
        self.assertIn("behavior_events", table_names)
        self.assertIn("assistant_action_permissions", table_names)
        self.assertIn("assistant_action_audit", table_names)
        self.assertIn("pet_state", table_names)
        self.assertIn("pet_state_history", table_names)
        self.assertIn("summary", conversation_columns)
        self.assertIn("archived_at", memory_columns)
        self.assertIn("embedding_json", memory_columns)
        self.assertIn("english_translation", message_columns)
        self.assertEqual(
            versions,
            [(1,), (2,), (3,), (4,), (5,), (6,), (7,), (8,), (9,)],
        )

    def test_applies_assistant_action_migration_to_existing_database(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            migrations_dir = root / "migrations"
            migrations_dir.mkdir()
            project_root = Path(__file__).resolve().parents[3]
            source_dir = project_root / "project_akiha" / "database" / "migrations"
            for source in sorted(source_dir.glob("000[1-7]_*.sql")):
                shutil.copy2(source, migrations_dir / source.name)

            database_path = root / "akiha.sqlite3"
            migrator = DatabaseMigrator(
                database_path,
                migrations_dir=migrations_dir,
            )
            migrator.apply_pending()
            shutil.copy2(
                source_dir / "0008_assistant_actions.sql",
                migrations_dir / "0008_assistant_actions.sql",
            )
            migrator.apply_pending()

            connection = sqlite3.connect(database_path)
            try:
                versions = connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                ).fetchall()
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(
            versions,
            [(1,), (2,), (3,), (4,), (5,), (6,), (7,), (8,)],
        )
        self.assertIn("assistant_action_permissions", tables)
        self.assertIn("assistant_action_audit", tables)

    def test_applies_pet_state_migration_to_existing_database(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            migrations_dir = root / "migrations"
            migrations_dir.mkdir()
            project_root = Path(__file__).resolve().parents[3]
            source_dir = project_root / "project_akiha" / "database" / "migrations"
            for source in sorted(source_dir.glob("000[1-8]_*.sql")):
                shutil.copy2(source, migrations_dir / source.name)

            database_path = root / "akiha.sqlite3"
            migrator = DatabaseMigrator(
                database_path,
                migrations_dir=migrations_dir,
            )
            migrator.apply_pending()
            shutil.copy2(
                source_dir / "0009_pet_state.sql",
                migrations_dir / "0009_pet_state.sql",
            )
            migrator.apply_pending()

            connection = sqlite3.connect(database_path)
            try:
                versions = connection.execute(
                    "SELECT version FROM schema_version ORDER BY version"
                ).fetchall()
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            finally:
                connection.close()

        self.assertEqual(
            versions,
            [(1,), (2,), (3,), (4,), (5,), (6,), (7,), (8,), (9,)],
        )
        self.assertIn("pet_state", tables)
        self.assertIn("pet_state_history", tables)

    def test_logs_migration_sql_failure_before_reraising(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            migrations_dir = root / "migrations"
            migrations_dir.mkdir()
            (migrations_dir / "0001_bad.sql").write_text(
                "CREATE TABLE broken (id INTEGER PRIMARY KEY",
                encoding="utf-8",
            )
            migrator = DatabaseMigrator(
                root / "akiha.sqlite3",
                migrations_dir=migrations_dir,
            )
            logger_name = "project_akiha.database.migrator"

            with self.assertLogs(logger_name, level="ERROR") as captured:
                with self.assertRaises(sqlite3.Error):
                    migrator.apply_pending()

        output = "\n".join(captured.output)
        self.assertIn("Database migration failed", output)
        self.assertIn("0001_bad.sql", output)

    def test_logs_invalid_migration_filename_before_reraising(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            migrations_dir = root / "migrations"
            migrations_dir.mkdir()
            (migrations_dir / "bad.sql").write_text("SELECT 1;", encoding="utf-8")
            migrator = DatabaseMigrator(
                root / "akiha.sqlite3",
                migrations_dir=migrations_dir,
            )
            logger_name = "project_akiha.database.migrator"

            with self.assertLogs(logger_name, level="ERROR") as captured:
                with self.assertRaises(ValueError):
                    migrator.apply_pending()

        self.assertIn("Database migration failed", captured.output[0])
        self.assertIn("migrations", captured.output[0])


if __name__ == "__main__":
    unittest.main()
