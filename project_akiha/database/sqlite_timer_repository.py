"""Minimal durable timers with atomic expiry and inbox receipts."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from project_akiha.core.utilities.timers import (
    MAX_ACTIVE_TIMERS,
    TimerRecord,
    TimerStatus,
)
from project_akiha.database.migrator import DatabaseMigrator


class SQLiteTimerRepository:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        DatabaseMigrator(database_path).apply_pending()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=5)

    def create(self, record: TimerRecord) -> TimerRecord:
        if (
            record.status is not TimerStatus.PENDING
            or record.notification_id is not None
        ):
            raise ValueError("Only new pending timer records can be created.")
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM utility_timers WHERE request_id=?", (record.request_id,)
            ).fetchone()
            if row:
                existing = _record(row)
                if existing.request_digest != record.request_digest:
                    raise ValueError("Timer request identity changed.")
                return existing
            count = connection.execute(
                "SELECT count(*) FROM utility_timers WHERE status='pending'"
            ).fetchone()[0]
            if count >= MAX_ACTIVE_TIMERS:
                raise ValueError("At most 100 timers may be active.")
            connection.execute(
                "INSERT INTO utility_timers VALUES (?,?,?,?,?,?,?,'pending',NULL,NULL)",
                (
                    record.timer_id,
                    record.request_id,
                    record.request_digest,
                    record.label,
                    record.duration_seconds,
                    _stamp(record.created_at),
                    _stamp(record.due_at),
                ),
            )
        return record

    def pending(self) -> tuple[TimerRecord, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM utility_timers WHERE status='pending' "
                "ORDER BY due_at,timer_id"
            ).fetchall()
        return tuple(_record(row) for row in rows)

    def get(self, timer_id: str) -> TimerRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM utility_timers WHERE timer_id=?", (timer_id,)
            ).fetchone()
        return _record(row) if row else None

    def cancel(self, timer_id: str, now: datetime) -> bool:
        with closing(self._connect()) as connection, connection:
            changed = connection.execute(
                "UPDATE utility_timers SET status='cancelled',completed_at=? "
                "WHERE timer_id=? AND status='pending'",
                (_stamp(now), timer_id),
            ).rowcount
        return changed == 1

    def claim_expiry(
        self, timer_id: str, now: datetime, *, missed: bool
    ) -> TimerRecord | None:
        # Receipt and inbox entry commit together, before any external presentation.
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM utility_timers WHERE timer_id=? AND status='pending'",
                (timer_id,),
            ).fetchone()
            if row is None:
                return None
            timer = _record(row)
            text = (
                f"Timer {timer_id} elapsed."
                if not missed
                else f"Timer {timer_id} elapsed while Akiha was closed."
            )
            cursor = connection.execute(
                "INSERT INTO notification_inbox(service,event_kind,priority,"
                "display_text,occurred_at,created_at,delivery_status) "
                "VALUES ('timers','timers.elapsed',"
                "'normal',?,?,?,?)",
                (
                    text,
                    _stamp(timer.due_at),
                    _stamp(now),
                    "silent" if missed else "pending",
                ),
            )
            connection.execute(
                "UPDATE utility_timers SET status=?,completed_at=?,notification_id=? "
                "WHERE timer_id=?",
                (
                    "missed" if missed else "elapsed",
                    _stamp(now),
                    cursor.lastrowid,
                    timer_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM utility_timers WHERE timer_id=?", (timer_id,)
            ).fetchone()
        return _record(row)


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timer timestamps require a timezone.")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def _record(row) -> TimerRecord:
    return TimerRecord(
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        datetime.fromisoformat(row[5]),
        datetime.fromisoformat(row[6]),
        TimerStatus(row[7]),
        row[9],
    )
