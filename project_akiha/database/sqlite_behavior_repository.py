"""SQLite-backed repository for behavior history events."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

from project_akiha.core.behavior import BehaviorEvent
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteBehaviorRepository:
    """Persist proactive behavior history in the local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def record_event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        kind: str | None = None,
    ) -> BehaviorEvent:
        """Persist one behavior event."""
        normalized_event_type = event_type.strip()
        if not normalized_event_type:
            raise ValueError("behavior event_type cannot be empty.")

        normalized_kind = kind.strip() if kind is not None else None
        if normalized_kind == "":
            normalized_kind = None

        return await asyncio.to_thread(
            self._record_event,
            normalized_event_type,
            dict(payload),
            normalized_kind,
        )

    async def get_recent_events(self, limit: int) -> tuple[BehaviorEvent, ...]:
        """Return recent behavior events ordered newest first."""
        if limit <= 0:
            raise ValueError("behavior event limit must be greater than zero.")

        return await asyncio.to_thread(self._get_recent_events, limit)

    async def clear_events(self) -> None:
        """Delete all behavior history."""
        await asyncio.to_thread(self._clear_events)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        kind: str | None,
    ) -> BehaviorEvent:
        timestamp = _utc_timestamp()
        payload_json = json.dumps(payload, sort_keys=True)
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO behavior_events(event_type, kind, payload_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_type, kind, payload_json, timestamp),
            )
            event_id = int(cursor.lastrowid)
            row = connection.execute(
                """
                SELECT id, event_type, kind, payload_json, created_at
                FROM behavior_events
                WHERE id = ?
                """,
                (event_id,),
            ).fetchone()
            connection.commit()
            return _event_from_row(row)
        finally:
            connection.close()

    def _get_recent_events(self, limit: int) -> tuple[BehaviorEvent, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, event_type, kind, payload_json, created_at
                FROM behavior_events
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_event_from_row(row) for row in rows)

    def _clear_events(self) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM behavior_events")
            connection.commit()
        finally:
            connection.close()


def _event_from_row(row: sqlite3.Row) -> BehaviorEvent:
    payload = json.loads(str(row["payload_json"]))
    if not isinstance(payload, dict):
        payload = {}

    return BehaviorEvent(
        id=int(row["id"]),
        event_type=str(row["event_type"]),
        kind=str(row["kind"]) if row["kind"] is not None else None,
        payload=MappingProxyType(payload),
        created_at=str(row["created_at"]),
    )


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
