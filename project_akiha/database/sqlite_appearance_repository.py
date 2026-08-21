"""SQLite persistence for the selected complete Akiha appearance."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.appearance import AppearanceId, AppearanceSelection
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteAppearanceRepository:
    """Persist the singleton appearance selection without touching inventory."""

    def __init__(self, database_path: Path) -> None:
        if not isinstance(database_path, Path):
            raise TypeError("database_path must be a Path value.")
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def get_selection(self) -> AppearanceSelection:
        """Return the durable selection created by migration 0012."""
        return await asyncio.to_thread(self._get_selection)

    async def save_selection(
        self,
        selection: AppearanceSelection,
    ) -> AppearanceSelection:
        """Atomically replace and return the singleton selection."""
        if not isinstance(selection, AppearanceSelection):
            raise TypeError("selection must be an AppearanceSelection value.")
        return await asyncio.to_thread(self._save_selection, selection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _get_selection(self) -> AppearanceSelection:
        connection = self._connect()
        try:
            row = connection.execute("""
                SELECT appearance_id, selected_at
                FROM pet_appearance_selection
                WHERE id = 1
                """).fetchone()
        finally:
            connection.close()
        if row is None:
            raise RuntimeError("appearance selection was not initialized.")
        return _selection_from_row(row)

    def _save_selection(
        self,
        selection: AppearanceSelection,
    ) -> AppearanceSelection:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO pet_appearance_selection(id, appearance_id, selected_at)
                VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    appearance_id = excluded.appearance_id,
                    selected_at = excluded.selected_at
                """,
                (
                    selection.appearance_id.value,
                    selection.selected_at.astimezone(UTC).isoformat(
                        timespec="microseconds"
                    ),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return selection


def _selection_from_row(row: sqlite3.Row) -> AppearanceSelection:
    selected_at = datetime.fromisoformat(str(row["selected_at"]))
    if selected_at.tzinfo is None or selected_at.utcoffset() is None:
        raise ValueError("persisted appearance timestamp must be timezone-aware.")
    return AppearanceSelection(
        appearance_id=AppearanceId(str(row["appearance_id"])),
        selected_at=selected_at.astimezone(UTC),
    )
