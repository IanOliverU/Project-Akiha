"""SQLite persistence for sanitized Notification Center records."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.integrations import (
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.core.notifications import (
    NotificationInboxRecord,
    NotificationInboxStatus,
    SanitizedNotification,
)
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteNotificationRepository:
    """Persist only bounded rendered notices and allowlisted metadata."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    def add(self, notification: SanitizedNotification) -> int:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO notification_inbox(
                    service, event_kind, priority, display_text, occurred_at,
                    created_at, delivery_status, aggregate_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification.service.value,
                    notification.event_kind.value,
                    notification.priority.value,
                    notification.display_text,
                    _timestamp(notification.occurred_at),
                    _timestamp(notification.created_at),
                    notification.status.value,
                    notification.aggregate_count,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
        finally:
            connection.close()

    def list_recent(
        self, *, limit: int = 200, unread_only: bool = False
    ) -> tuple[NotificationInboxRecord, ...]:
        if not 1 <= limit <= 500:
            raise ValueError("Notification query limit must be between 1 and 500.")
        where = "WHERE read_at IS NULL" if unread_only else ""
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT id, service, event_kind, priority, display_text,
                       occurred_at, created_at, read_at, delivery_status,
                       aggregate_count
                FROM notification_inbox
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_record_from_row(row) for row in rows)

    def update_status(self, record_id: int, status: NotificationInboxStatus) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "UPDATE notification_inbox SET delivery_status = ? WHERE id = ?",
                (status.value, _positive_id(record_id)),
            )
            connection.commit()
        finally:
            connection.close()

    def mark_read(self, record_ids: tuple[int, ...], *, read_at: datetime) -> int:
        ids = tuple(dict.fromkeys(_positive_id(value) for value in record_ids))
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        connection = self._connect()
        try:
            cursor = connection.execute(
                f"""
                UPDATE notification_inbox
                SET read_at = ?
                WHERE read_at IS NULL AND id IN ({placeholders})
                """,
                (_timestamp(read_at), *ids),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def mark_all_read(self, *, read_at: datetime) -> int:
        connection = self._connect()
        try:
            cursor = connection.execute(
                "UPDATE notification_inbox SET read_at = ? WHERE read_at IS NULL",
                (_timestamp(read_at),),
            )
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def clear(self) -> int:
        connection = self._connect()
        try:
            cursor = connection.execute("DELETE FROM notification_inbox")
            connection.commit()
            return cursor.rowcount
        finally:
            connection.close()

    def prune(self, *, maximum_records: int, older_than: datetime) -> int:
        if not 1 <= maximum_records <= 10_000:
            raise ValueError("Notification retention limit is out of range.")
        connection = self._connect()
        try:
            age_cursor = connection.execute(
                "DELETE FROM notification_inbox WHERE created_at < ?",
                (_timestamp(older_than),),
            )
            count_cursor = connection.execute(
                """
                DELETE FROM notification_inbox
                WHERE id NOT IN (
                    SELECT id FROM notification_inbox
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                )
                """,
                (maximum_records,),
            )
            connection.commit()
            return age_cursor.rowcount + count_cursor.rowcount
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _record_from_row(row: tuple[object, ...]) -> NotificationInboxRecord:
    return NotificationInboxRecord(
        id=int(row[0]),
        service=ExternalService(str(row[1])),
        event_kind=ExternalEventKind(str(row[2])),
        priority=ExternalEventPriority(str(row[3])),
        display_text=str(row[4]),
        occurred_at=_parse_timestamp(str(row[5])),
        created_at=_parse_timestamp(str(row[6])),
        read_at=_parse_timestamp(str(row[7])) if row[7] is not None else None,
        status=NotificationInboxStatus(str(row[8])),
        aggregate_count=int(row[9]),
    )


def _positive_id(value: int) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError("Notification record id must be positive.")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Notification timestamps must be timezone-aware.")
    return value.astimezone(UTC).isoformat(timespec="seconds")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed
