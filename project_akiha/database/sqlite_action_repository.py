"""SQLite persistence for assistant permissions and sanitized action audit."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.actions import (
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
    ActionAuditEntry,
    ActionFailureCategory,
    ActionStatus,
    PermissionDecision,
    PermissionGrant,
)
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteActionRepository:
    """Persist Phase 8 permission grants and action evaluation history."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        DatabaseMigrator(database_path).apply_pending()

    async def grant_permission(
        self,
        capability: str,
        target: str,
    ) -> PermissionGrant:
        """Create or return an active capability-target grant."""
        normalized_capability = _required_text(capability, "permission capability")
        normalized_target = _required_text(target, "permission target")
        return await asyncio.to_thread(
            self._grant_permission,
            normalized_capability,
            normalized_target,
        )

    async def get_active_permissions(
        self,
        capability: str | None = None,
    ) -> tuple[PermissionGrant, ...]:
        """Return active grants ordered by creation and identifier."""
        normalized_capability = (
            _required_text(capability, "permission capability")
            if capability is not None
            else None
        )
        return await asyncio.to_thread(
            self._get_active_permissions,
            normalized_capability,
        )

    async def revoke_permission(self, permission_id: int) -> bool:
        """Revoke one active permission."""
        if permission_id <= 0:
            raise ValueError("permission id must be greater than zero.")
        return await asyncio.to_thread(self._revoke_permission, permission_id)

    async def set_directory_permissions(
        self,
        target: str,
        *,
        allow_search: bool,
        allow_open: bool,
    ) -> tuple[PermissionGrant, ...]:
        """Atomically replace active file permissions for one directory."""
        if not isinstance(allow_search, bool) or not isinstance(allow_open, bool):
            raise TypeError("directory permission flags must be boolean.")
        return await asyncio.to_thread(
            self._set_directory_permissions,
            _required_text(target, "directory permission target"),
            allow_search,
            allow_open,
        )

    async def revoke_directory_permissions(self, target: str) -> int:
        """Atomically revoke all active file permissions for one directory."""
        return await asyncio.to_thread(
            self._revoke_directory_permissions,
            _required_text(target, "directory permission target"),
        )

    async def record_action_audit(
        self,
        *,
        correlation_id: str,
        action_id: str,
        source: str,
        normalized_target: str | None,
        permission_decision: PermissionDecision,
        result_status: ActionStatus,
        duration_ms: int,
        failure_category: ActionFailureCategory | None,
    ) -> ActionAuditEntry:
        """Persist one bounded action evaluation record."""
        if duration_ms < 0:
            raise ValueError("action duration_ms cannot be negative.")
        return await asyncio.to_thread(
            self._record_action_audit,
            _required_text(correlation_id, "action correlation_id"),
            _required_text(action_id, "action identifier"),
            _required_text(source, "action source"),
            normalized_target.strip() if normalized_target else None,
            permission_decision,
            result_status,
            duration_ms,
            failure_category,
        )

    async def get_recent_action_audits(
        self,
        limit: int,
    ) -> tuple[ActionAuditEntry, ...]:
        """Return recent audit entries ordered newest first."""
        if limit <= 0:
            raise ValueError("action audit limit must be greater than zero.")
        return await asyncio.to_thread(self._get_recent_action_audits, limit)

    async def clear_action_audits(self) -> int:
        """Delete all sanitized action audit rows."""
        return await asyncio.to_thread(self._clear_action_audits)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _grant_permission(
        self,
        capability: str,
        target: str,
    ) -> PermissionGrant:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT id, capability, target, created_at, revoked_at
                FROM assistant_action_permissions
                WHERE capability = ? AND target = ? AND revoked_at IS NULL
                """,
                (capability, target),
            ).fetchone()
            if row is None:
                timestamp = _utc_timestamp()
                cursor = connection.execute(
                    """
                    INSERT INTO assistant_action_permissions(
                        capability,
                        target,
                        created_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (capability, target, timestamp),
                )
                row = connection.execute(
                    """
                    SELECT id, capability, target, created_at, revoked_at
                    FROM assistant_action_permissions
                    WHERE id = ?
                    """,
                    (int(cursor.lastrowid),),
                ).fetchone()
                connection.commit()
            return _permission_from_row(row)
        finally:
            connection.close()

    def _get_active_permissions(
        self,
        capability: str | None,
    ) -> tuple[PermissionGrant, ...]:
        connection = self._connect()
        try:
            if capability is None:
                rows = connection.execute("""
                    SELECT id, capability, target, created_at, revoked_at
                    FROM assistant_action_permissions
                    WHERE revoked_at IS NULL
                    ORDER BY created_at, id
                    """).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, capability, target, created_at, revoked_at
                    FROM assistant_action_permissions
                    WHERE revoked_at IS NULL AND capability = ?
                    ORDER BY created_at, id
                    """,
                    (capability,),
                ).fetchall()
        finally:
            connection.close()
        return tuple(_permission_from_row(row) for row in rows)

    def _revoke_permission(self, permission_id: int) -> bool:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE assistant_action_permissions
                SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (_utc_timestamp(), permission_id),
            )
            connection.commit()
            return cursor.rowcount > 0
        finally:
            connection.close()

    def _set_directory_permissions(
        self,
        target: str,
        allow_search: bool,
        allow_open: bool,
    ) -> tuple[PermissionGrant, ...]:
        requested = {
            FILE_SEARCH_CAPABILITY: allow_search,
            FILE_OPEN_CAPABILITY: allow_open,
        }
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            for capability, enabled in requested.items():
                row = connection.execute(
                    """
                    SELECT id
                    FROM assistant_action_permissions
                    WHERE capability = ? AND target = ? AND revoked_at IS NULL
                    """,
                    (capability, target),
                ).fetchone()
                if enabled and row is None:
                    connection.execute(
                        """
                        INSERT INTO assistant_action_permissions(
                            capability,
                            target,
                            created_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (capability, target, timestamp),
                    )
                elif not enabled and row is not None:
                    connection.execute(
                        """
                        UPDATE assistant_action_permissions
                        SET revoked_at = ?
                        WHERE id = ?
                        """,
                        (timestamp, int(row["id"])),
                    )

            rows = connection.execute(
                """
                SELECT id, capability, target, created_at, revoked_at
                FROM assistant_action_permissions
                WHERE target = ?
                  AND capability IN (?, ?)
                  AND revoked_at IS NULL
                ORDER BY capability, id
                """,
                (
                    target,
                    FILE_OPEN_CAPABILITY,
                    FILE_SEARCH_CAPABILITY,
                ),
            ).fetchall()
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return tuple(_permission_from_row(row) for row in rows)

    def _revoke_directory_permissions(self, target: str) -> int:
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                UPDATE assistant_action_permissions
                SET revoked_at = ?
                WHERE target = ?
                  AND capability IN (?, ?)
                  AND revoked_at IS NULL
                """,
                (
                    _utc_timestamp(),
                    target,
                    FILE_OPEN_CAPABILITY,
                    FILE_SEARCH_CAPABILITY,
                ),
            )
            connection.commit()
            return int(cursor.rowcount)
        finally:
            connection.close()

    def _record_action_audit(
        self,
        correlation_id: str,
        action_id: str,
        source: str,
        normalized_target: str | None,
        permission_decision: PermissionDecision,
        result_status: ActionStatus,
        duration_ms: int,
        failure_category: ActionFailureCategory | None,
    ) -> ActionAuditEntry:
        timestamp = _utc_timestamp()
        connection = self._connect()
        try:
            cursor = connection.execute(
                """
                INSERT INTO assistant_action_audit(
                    correlation_id,
                    action_id,
                    source,
                    normalized_target,
                    permission_decision,
                    result_status,
                    duration_ms,
                    failure_category,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    correlation_id,
                    action_id,
                    source,
                    normalized_target,
                    permission_decision.value,
                    result_status.value,
                    duration_ms,
                    failure_category.value if failure_category is not None else None,
                    timestamp,
                ),
            )
            row = connection.execute(
                """
                SELECT id, correlation_id, action_id, source, normalized_target,
                       permission_decision, result_status, duration_ms,
                       failure_category, created_at
                FROM assistant_action_audit
                WHERE id = ?
                """,
                (int(cursor.lastrowid),),
            ).fetchone()
            connection.commit()
            return _audit_from_row(row)
        finally:
            connection.close()

    def _get_recent_action_audits(
        self,
        limit: int,
    ) -> tuple[ActionAuditEntry, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT id, correlation_id, action_id, source, normalized_target,
                       permission_decision, result_status, duration_ms,
                       failure_category, created_at
                FROM assistant_action_audit
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_audit_from_row(row) for row in rows)

    def _clear_action_audits(self) -> int:
        connection = self._connect()
        try:
            cursor = connection.execute("DELETE FROM assistant_action_audit")
            connection.commit()
            return int(cursor.rowcount)
        finally:
            connection.close()


def _permission_from_row(row: sqlite3.Row) -> PermissionGrant:
    return PermissionGrant(
        id=int(row["id"]),
        capability=str(row["capability"]),
        target=str(row["target"]),
        created_at=str(row["created_at"]),
        revoked_at=(str(row["revoked_at"]) if row["revoked_at"] is not None else None),
    )


def _audit_from_row(row: sqlite3.Row) -> ActionAuditEntry:
    failure_value = row["failure_category"]
    return ActionAuditEntry(
        id=int(row["id"]),
        correlation_id=str(row["correlation_id"]),
        action_id=str(row["action_id"]),
        source=str(row["source"]),
        normalized_target=(
            str(row["normalized_target"])
            if row["normalized_target"] is not None
            else None
        ),
        permission_decision=PermissionDecision(str(row["permission_decision"])),
        result_status=ActionStatus(str(row["result_status"])),
        duration_ms=int(row["duration_ms"]),
        failure_category=(
            ActionFailureCategory(str(failure_value))
            if failure_value is not None
            else None
        ),
        created_at=str(row["created_at"]),
    )


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    return normalized


def _utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
