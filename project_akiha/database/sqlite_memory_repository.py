"""SQLite-backed repository for durable companion memories."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from project_akiha.core.memory import MemoryEntry
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteMemoryRepository:
    """Persist durable memories in the local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def save_memory(
        self,
        content: str,
        source_conversation_id: int | None = None,
        importance: int = 3,
        tags: Sequence[str] = (),
    ) -> MemoryEntry:
        """Persist one durable memory."""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("memory content cannot be empty.")
        if not 1 <= importance <= 5:
            raise ValueError("memory importance must be between 1 and 5.")

        normalized_tags = _normalize_tags(tags)
        return await asyncio.to_thread(
            self._save_memory,
            normalized_content,
            source_conversation_id,
            importance,
            normalized_tags,
        )

    async def get_recent_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        """Return recent memories ordered newest first."""
        if limit <= 0:
            raise ValueError("memory limit must be greater than zero.")

        return await asyncio.to_thread(self._get_recent_memories, limit)

    async def get_archived_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        """Return archived memories ordered newest first."""
        if limit <= 0:
            raise ValueError("memory limit must be greater than zero.")

        return await asyncio.to_thread(self._get_archived_memories, limit)

    async def retrieve_relevant_memories(
        self,
        query: str,
        limit: int,
    ) -> tuple[MemoryEntry, ...]:
        """Return memories relevant to a user query."""
        if limit <= 0:
            raise ValueError("memory limit must be greater than zero.")

        normalized_query = query.strip().lower()
        if not normalized_query:
            return await self.get_recent_memories(limit)

        return await asyncio.to_thread(
            self._retrieve_relevant_memories,
            normalized_query,
            limit,
        )

    async def update_memory(
        self,
        memory_id: int,
        content: str,
        importance: int,
        tags: Sequence[str] = (),
    ) -> MemoryEntry:
        """Update one durable memory."""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("memory content cannot be empty.")
        if not 1 <= importance <= 5:
            raise ValueError("memory importance must be between 1 and 5.")

        normalized_tags = _normalize_tags(tags)
        return await asyncio.to_thread(
            self._update_memory,
            memory_id,
            normalized_content,
            importance,
            normalized_tags,
        )

    async def delete_memory(self, memory_id: int) -> None:
        """Delete one memory."""
        await asyncio.to_thread(self._delete_memory, memory_id)

    async def archive_memory(self, memory_id: int) -> None:
        """Move one memory out of active retrieval."""
        await asyncio.to_thread(self._archive_memory, memory_id)

    async def restore_memory(self, memory_id: int) -> None:
        """Move one archived memory back into active retrieval."""
        await asyncio.to_thread(self._restore_memory, memory_id)

    async def clear_memories(self) -> None:
        """Delete all memories."""
        await asyncio.to_thread(self._clear_memories)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _save_memory(
        self,
        content: str,
        source_conversation_id: int | None,
        importance: int,
        tags: tuple[str, ...],
    ) -> MemoryEntry:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO memories(
                    content,
                    source_conversation_id,
                    importance,
                    tags_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    content,
                    source_conversation_id,
                    importance,
                    json.dumps(tags),
                    timestamp,
                    timestamp,
                ),
            )
            memory_id = int(cursor.lastrowid)
            row = connection.execute(
                """
                SELECT id, content, source_conversation_id, importance, tags_json,
                       created_at, updated_at, last_accessed_at, archived_at
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
            connection.commit()
            return _memory_from_row(row)
        finally:
            connection.close()

    def _get_recent_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, content, source_conversation_id, importance, tags_json,
                       created_at, updated_at, last_accessed_at, archived_at
                FROM memories
                WHERE archived_at IS NULL
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_memory_from_row(row) for row in rows)

    def _get_archived_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, content, source_conversation_id, importance, tags_json,
                       created_at, updated_at, last_accessed_at, archived_at
                FROM memories
                WHERE archived_at IS NOT NULL
                ORDER BY archived_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_memory_from_row(row) for row in rows)

    def _retrieve_relevant_memories(
        self,
        query: str,
        limit: int,
    ) -> tuple[MemoryEntry, ...]:
        pattern = f"%{query}%"
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, content, source_conversation_id, importance, tags_json,
                       created_at, updated_at, last_accessed_at, archived_at
                FROM memories
                WHERE archived_at IS NULL
                    AND (lower(content) LIKE ? OR lower(tags_json) LIKE ?)
                ORDER BY importance DESC, updated_at DESC, id DESC
                LIMIT ?
                """,
                (pattern, pattern, limit),
            ).fetchall()
            memory_ids = [int(row["id"]) for row in rows]
            if memory_ids:
                connection.executemany(
                    """
                    UPDATE memories
                    SET last_accessed_at = ?
                    WHERE id = ?
                    """,
                    [(timestamp, memory_id) for memory_id in memory_ids],
                )
                connection.commit()
        finally:
            connection.close()

        return tuple(_memory_from_row(row) for row in rows)

    def _update_memory(
        self,
        memory_id: int,
        content: str,
        importance: int,
        tags: tuple[str, ...],
    ) -> MemoryEntry:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE memories
                SET content = ?,
                    importance = ?,
                    tags_json = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (content, importance, json.dumps(tags), timestamp, memory_id),
            )
            row = connection.execute(
                """
                SELECT id, content, source_conversation_id, importance, tags_json,
                       created_at, updated_at, last_accessed_at, archived_at
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
            connection.commit()
            if row is None:
                raise ValueError("memory was not found.")
            return _memory_from_row(row)
        finally:
            connection.close()

    def _delete_memory(self, memory_id: int) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            connection.commit()
        finally:
            connection.close()

    def _archive_memory(self, memory_id: int) -> None:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE memories
                SET archived_at = ?,
                    updated_at = ?
                WHERE id = ? AND archived_at IS NULL
                """,
                (timestamp, timestamp, memory_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _restore_memory(self, memory_id: int) -> None:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE memories
                SET archived_at = NULL,
                    updated_at = ?
                WHERE id = ? AND archived_at IS NOT NULL
                """,
                (timestamp, memory_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _clear_memories(self) -> None:
        connection = self._connect()
        try:
            connection.execute("DELETE FROM memories")
            connection.commit()
        finally:
            connection.close()


def _memory_from_row(row: sqlite3.Row) -> MemoryEntry:
    return MemoryEntry(
        id=int(row["id"]),
        content=str(row["content"]),
        source_conversation_id=cast(int | None, row["source_conversation_id"]),
        importance=int(row["importance"]),
        tags=tuple(json.loads(str(row["tags_json"]))),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        last_accessed_at=cast(str | None, row["last_accessed_at"]),
        archived_at=cast(str | None, row["archived_at"]),
    )


def _normalize_tags(tags: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip()).keys()
    )


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
