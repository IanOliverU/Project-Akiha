"""SQLite persistence for external-event dedupe and synchronization cursors."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.integrations import (
    ExternalEvent,
    ExternalNotificationStatus,
    ExternalService,
)
from project_akiha.database.migrator import DatabaseMigrator

_CURSOR_MAXIMUM = 512
_ACCOUNT_KEY_MAXIMUM = 256


class SQLiteExternalEventRepository:
    """Persist hashes and cursors without storing communication content."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    def claim_event(self, event: ExternalEvent, *, received_at: datetime) -> bool:
        """Atomically insert a minimal receipt unless it already exists."""
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO external_event_receipts(
                    service, external_id_hash, event_kind, occurred_at,
                    classification, priority, notification_status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.service.value,
                    _digest(event.external_id),
                    event.kind.value,
                    event.occurred_at.isoformat(),
                    event.classification.value,
                    event.priority.value,
                    ExternalNotificationStatus.RECEIVED.value,
                    _timestamp(received_at),
                ),
            )
            connection.commit()
            return cursor.rowcount == 1
        finally:
            connection.close()

    def set_notification_status(
        self,
        event: ExternalEvent,
        status: ExternalNotificationStatus,
        *,
        notified_at: datetime | None = None,
    ) -> None:
        """Update one claimed receipt without adding provider content."""
        connection = self._connect()
        try:
            connection.execute(
                """
                UPDATE external_event_receipts
                SET notification_status = ?, notified_at = ?
                WHERE service = ? AND external_id_hash = ?
                """,
                (
                    status.value,
                    _timestamp(notified_at) if notified_at is not None else None,
                    event.service.value,
                    _digest(event.external_id),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def load_sync_cursor(
        self, service: ExternalService, account_key: str
    ) -> str | None:
        """Load a cursor using only a hash of the local account key."""
        normalized_account = _bounded(account_key, "account key", _ACCOUNT_KEY_MAXIMUM)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT cursor
                FROM integration_sync_state
                WHERE service = ? AND account_key_hash = ?
                """,
                (service.value, _digest(normalized_account)),
            ).fetchone()
        finally:
            connection.close()
        return str(row[0]) if row is not None else None

    def save_sync_cursor(
        self,
        service: ExternalService,
        account_key: str,
        cursor: str,
        *,
        synchronized_at: datetime,
    ) -> None:
        """Upsert one bounded synchronization cursor."""
        normalized_account = _bounded(account_key, "account key", _ACCOUNT_KEY_MAXIMUM)
        normalized_cursor = _bounded(cursor, "sync cursor", _CURSOR_MAXIMUM)
        timestamp = _timestamp(synchronized_at)
        connection = self._connect()
        try:
            connection.execute(
                """
                INSERT INTO integration_sync_state(
                    service, account_key_hash, cursor,
                    last_successful_sync_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(service, account_key_hash) DO UPDATE SET
                    cursor = excluded.cursor,
                    last_successful_sync_at = excluded.last_successful_sync_at,
                    updated_at = excluded.updated_at
                """,
                (
                    service.value,
                    _digest(normalized_account),
                    normalized_cursor,
                    timestamp,
                    timestamp,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _bounded(value: str, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"External integration {label} cannot be empty.")
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ValueError(f"External integration {label} is too long.")
    return normalized


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("External integration timestamps must be timezone-aware.")
    return value.astimezone(UTC).isoformat(timespec="seconds")
