"""Tests for SQLite behavior history persistence."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.database import SQLiteBehaviorRepository


class SQLiteBehaviorRepositoryTest(unittest.TestCase):
    """Verify behavior event persistence and retrieval."""

    def test_records_and_loads_recent_events(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteBehaviorRepository(Path(directory) / "akiha.sqlite3")

            first = asyncio.run(
                repository.record_event(
                    "proactive.suggestion_ready",
                    {"kind": "idle_check_in", "message": "Need a break?"},
                    kind="idle_check_in",
                )
            )
            second = asyncio.run(
                repository.record_event(
                    "proactive.suggestion_delivered",
                    {"kind": "idle_check_in", "delivered": True},
                    kind="idle_check_in",
                )
            )

            events = asyncio.run(repository.get_recent_events(limit=10))

        self.assertEqual([event.id for event in events], [second.id, first.id])
        self.assertEqual(events[0].event_type, "proactive.suggestion_delivered")
        self.assertEqual(events[0].kind, "idle_check_in")
        self.assertTrue(events[0].payload["delivered"])
        self.assertNotEqual(events[0].created_at, "")

    def test_record_event_normalizes_empty_kind(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteBehaviorRepository(Path(directory) / "akiha.sqlite3")

            event = asyncio.run(
                repository.record_event(
                    "mood.state_changed",
                    {"mood": "calm"},
                    kind="   ",
                )
            )

        self.assertIsNone(event.kind)

    def test_record_event_rejects_empty_event_type(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteBehaviorRepository(Path(directory) / "akiha.sqlite3")

            with self.assertRaises(ValueError):
                asyncio.run(repository.record_event("   ", {}))

    def test_get_recent_events_validates_limit(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteBehaviorRepository(Path(directory) / "akiha.sqlite3")

            with self.assertRaises(ValueError):
                asyncio.run(repository.get_recent_events(limit=0))

    def test_clear_events_deletes_history(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteBehaviorRepository(Path(directory) / "akiha.sqlite3")
            asyncio.run(repository.record_event("proactive.suggestion_ready", {}))

            asyncio.run(repository.clear_events())
            events = asyncio.run(repository.get_recent_events(limit=10))

        self.assertEqual(events, ())

    def test_migration_creates_behavior_events_table(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "akiha.sqlite3"
            SQLiteBehaviorRepository(database_path)

            connection = sqlite3.connect(database_path)
            try:
                row = connection.execute("""
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'behavior_events'
                    """).fetchone()
            finally:
                connection.close()

        self.assertEqual(row[0], "behavior_events")


if __name__ == "__main__":
    unittest.main()
