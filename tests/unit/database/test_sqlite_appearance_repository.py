"""Tests for durable complete-appearance selection."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.appearance import AppearanceId, AppearanceSelection
from project_akiha.database import SQLiteAppearanceRepository


class SQLiteAppearanceRepositoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_migration_defaults_to_seifuku_and_selection_survives_restart(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "akiha.sqlite3"
            repository = SQLiteAppearanceRepository(path)
            default = await repository.get_selection()
            selected = AppearanceSelection(
                AppearanceId.DRESS,
                datetime(2026, 8, 22, 10, 0, tzinfo=UTC),
            )
            await repository.save_selection(selected)
            restarted = SQLiteAppearanceRepository(path)

            self.assertIs(default.appearance_id, AppearanceId.SEIFUKU)
            self.assertEqual(await restarted.get_selection(), selected)

    async def test_rejects_untyped_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = SQLiteAppearanceRepository(Path(directory) / "akiha.sqlite3")
            with self.assertRaises(TypeError):
                await repository.save_selection("dress")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
