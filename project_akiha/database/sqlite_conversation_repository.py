"""SQLite-backed repository for raw conversation transcripts."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from project_akiha.core.memory import Conversation, MessageRole, StoredMessage
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteConversationRepository:
    """Persist conversation transcripts in a local SQLite database."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def create_conversation(self, title: str = "Current chat") -> Conversation:
        """Create a new open conversation."""
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("conversation title cannot be empty.")

        return await asyncio.to_thread(self._create_conversation, normalized_title)

    async def get_or_create_current_conversation(self) -> Conversation:
        """Return the newest open conversation, creating one when needed."""
        return await asyncio.to_thread(self._get_or_create_current_conversation)

    async def close_conversation(self, conversation_id: int) -> None:
        """Mark a conversation as closed."""
        await asyncio.to_thread(self._close_conversation, conversation_id)

    async def clear_conversation_messages(self, conversation_id: int) -> None:
        """Delete all messages in a conversation."""
        await asyncio.to_thread(self._clear_conversation_messages, conversation_id)

    async def save_message(
        self,
        conversation_id: int,
        role: MessageRole,
        content: str,
    ) -> StoredMessage:
        """Persist one transcript message."""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("message content cannot be empty.")

        return await asyncio.to_thread(
            self._save_message,
            conversation_id,
            role,
            normalized_content,
        )

    async def get_recent_messages(
        self,
        conversation_id: int,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        """Return recent transcript messages in chronological order."""
        if limit <= 0:
            raise ValueError("message limit must be greater than zero.")

        return await asyncio.to_thread(
            self._get_recent_messages,
            conversation_id,
            limit,
        )

    async def get_messages(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Return all transcript messages in chronological order."""
        return await asyncio.to_thread(self._get_messages, conversation_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _create_conversation(self, title: str) -> Conversation:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO conversations(title, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (title, timestamp, timestamp),
            )
            conversation_id = int(cursor.lastrowid)
            row = connection.execute(
                """
                SELECT id, title, created_at, updated_at, closed_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
            connection.commit()
            return _conversation_from_row(row)
        finally:
            connection.close()

    def _get_or_create_current_conversation(self) -> Conversation:
        connection = self._connect()
        try:
            row = connection.execute("""
                SELECT id, title, created_at, updated_at, closed_at
                FROM conversations
                WHERE closed_at IS NULL
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """).fetchone()

            if row is None:
                timestamp = _utc_timestamp()
                cursor = connection.execute(
                    """
                    INSERT INTO conversations(title, created_at, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    ("Current chat", timestamp, timestamp),
                )
                conversation_id = int(cursor.lastrowid)
                row = connection.execute(
                    """
                    SELECT id, title, created_at, updated_at, closed_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                connection.commit()

            return _conversation_from_row(row)
        finally:
            connection.close()

    def _close_conversation(self, conversation_id: int) -> None:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE conversations
                SET closed_at = ?, updated_at = ?
                WHERE id = ? AND closed_at IS NULL
                """,
                (timestamp, timestamp, conversation_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _clear_conversation_messages(self, conversation_id: int) -> None:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            connection.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            )
            connection.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (timestamp, conversation_id),
            )
            connection.commit()
        finally:
            connection.close()

    def _save_message(
        self,
        conversation_id: int,
        role: MessageRole,
        content: str,
    ) -> StoredMessage:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO messages(conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, timestamp),
            )
            connection.execute(
                """
                UPDATE conversations
                SET updated_at = ?
                WHERE id = ?
                """,
                (timestamp, conversation_id),
            )
            message_id = int(cursor.lastrowid)
            row = connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM messages
                WHERE id = ?
                """,
                (message_id,),
            ).fetchone()
            connection.commit()
            return _message_from_row(row)
        finally:
            connection.close()

    def _get_recent_messages(
        self,
        conversation_id: int,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM (
                    SELECT id, conversation_id, role, content, created_at
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id, limit),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_message_from_row(row) for row in rows)

    def _get_messages(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (conversation_id,),
            ).fetchall()
        finally:
            connection.close()

        return tuple(_message_from_row(row) for row in rows)


def _conversation_from_row(row: sqlite3.Row) -> Conversation:
    return Conversation(
        id=int(row["id"]),
        title=str(row["title"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        closed_at=cast(str | None, row["closed_at"]),
    )


def _message_from_row(row: sqlite3.Row) -> StoredMessage:
    return StoredMessage(
        id=int(row["id"]),
        conversation_id=int(row["conversation_id"]),
        role=cast(MessageRole, row["role"]),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
    )


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
