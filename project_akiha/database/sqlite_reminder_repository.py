"""Minimal reminders and atomic, sanitized notification receipts."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from project_akiha.core.utilities.reminders import ReminderRecord
from project_akiha.core.utilities.timers import MAX_ACTIVE_TIMERS, TimerStatus
from project_akiha.database.migrator import DatabaseMigrator
from project_akiha.database.sqlite_timer_repository import _stamp


class SQLiteReminderRepository:
    def __init__(self, database_path: Path) -> None:
        self._path = database_path
        DatabaseMigrator(database_path).apply_pending()

    def _connect(self):
        return sqlite3.connect(self._path, timeout=5)

    def create(self, record: ReminderRecord) -> ReminderRecord:
        if (
            record.status is not TimerStatus.PENDING
            or record.notification_id is not None
        ):
            raise ValueError("Only new pending reminders can be created.")
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                "SELECT * FROM utility_reminders WHERE request_id=?",
                (record.request_id,),
            ).fetchone()
            if row:
                existing = _record(row)
                if existing.request_digest != record.request_digest:
                    raise ValueError("Reminder request identity changed.")
                return existing
            count = c.execute(
                "SELECT count(*) FROM utility_reminders WHERE status='pending'"
            ).fetchone()[0]
            if count >= MAX_ACTIVE_TIMERS:
                raise ValueError("At most 100 reminders may be active.")
            c.execute(
                (
                    "INSERT INTO utility_reminders VALUES "
                    "(?,?,?,?,?,?,?,'pending',NULL,NULL)"
                ),
                (
                    record.reminder_id,
                    record.request_id,
                    record.request_digest,
                    record.label,
                    record.timezone,
                    _stamp(record.created_at),
                    _stamp(record.due_at),
                ),
            )
        return record

    def pending(self) -> tuple[ReminderRecord, ...]:
        with closing(self._connect()) as c:
            rows = c.execute(
                "SELECT * FROM utility_reminders WHERE "
                "status='pending' ORDER BY due_at,reminder_id"
            ).fetchall()
        return tuple(_record(row) for row in rows)

    def get(self, reminder_id: str) -> ReminderRecord | None:
        with closing(self._connect()) as c:
            row = c.execute(
                "SELECT * FROM utility_reminders WHERE reminder_id=?", (reminder_id,)
            ).fetchone()
        return _record(row) if row else None

    def cancel(self, reminder_id: str, now: datetime) -> bool:
        with closing(self._connect()) as c, c:
            changed = c.execute(
                (
                    "UPDATE utility_reminders SET "
                    "status='cancelled',completed_at=? WHERE "
                    "reminder_id=? AND status='pending'"
                ),
                (_stamp(now), reminder_id),
            ).rowcount
        return changed == 1

    def redact_terminal_labels(self, before: datetime) -> int:
        with closing(self._connect()) as c, c:
            return c.execute(
                (
                    "UPDATE utility_reminders SET label='' WHERE "
                    "status!='pending' AND completed_at<? AND "
                    "label!=''"
                ),
                (_stamp(before),),
            ).rowcount

    def snooze(
        self,
        request_id: str,
        digest: str,
        reminder_id: str,
        now: datetime,
        due_at: datetime,
    ) -> ReminderRecord:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            replay = c.execute(
                (
                    "SELECT request_digest FROM "
                    "utility_reminder_snoozes WHERE request_id=?"
                ),
                (request_id,),
            ).fetchone()
            row = c.execute(
                "SELECT * FROM utility_reminders WHERE reminder_id=?", (reminder_id,)
            ).fetchone()
            if row is None:
                raise ValueError("Reminder is unavailable.")
            record = _record(row)
            if replay:
                if replay[0] != digest:
                    raise ValueError("Snooze request identity changed.")
                return record
            if record.status is TimerStatus.CANCELLED:
                raise ValueError("Cancelled reminders cannot be snoozed.")
            if (
                record.status is not TimerStatus.PENDING
                and c.execute(
                    "SELECT count(*) FROM utility_reminders WHERE status='pending'"
                ).fetchone()[0]
                >= MAX_ACTIVE_TIMERS
            ):
                raise ValueError("At most 100 reminders may be active.")
            result = replace(
                record,
                created_at=now,
                due_at=due_at,
                status=TimerStatus.PENDING,
                notification_id=None,
            )
            c.execute(
                "INSERT INTO utility_reminder_snoozes VALUES (?,?,?,?)",
                (request_id, digest, reminder_id, _stamp(due_at)),
            )
            c.execute(
                (
                    "UPDATE utility_reminders SET "
                    "created_at=?,due_at=?,status='pending',completed"
                    "_at=NULL,notification_id=NULL WHERE "
                    "reminder_id=?"
                ),
                (_stamp(now), _stamp(due_at), reminder_id),
            )
        return result

    def claim_expiry(
        self, reminder_id: str, now: datetime, *, missed: bool
    ) -> ReminderRecord | None:
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute(
                (
                    "SELECT * FROM utility_reminders WHERE "
                    "reminder_id=? AND status='pending' AND due_at<=?"
                ),
                (reminder_id, _stamp(now)),
            ).fetchone()
            if row is None:
                return None
            record = _record(row)
            text = (
                f"Reminder {reminder_id} is due."
                if not missed
                else f"Reminder {reminder_id} was due while Akiha was closed."
            )
            receipt = c.execute(
                (
                    "INSERT INTO "
                    "notification_inbox(service,event_kind,priority,d"
                    "isplay_text,occurred_at,created_at,delivery_stat"
                    "us) VALUES "
                    "('reminders','reminders.due','normal',?,?,?,?)"
                ),
                (
                    text,
                    _stamp(record.due_at),
                    _stamp(now),
                    "silent" if missed else "pending",
                ),
            ).lastrowid
            c.execute(
                (
                    "UPDATE utility_reminders SET "
                    "status=?,completed_at=?,notification_id=? WHERE "
                    "reminder_id=?"
                ),
                ("missed" if missed else "elapsed", _stamp(now), receipt, reminder_id),
            )
            return replace(
                record,
                status=TimerStatus.MISSED if missed else TimerStatus.ELAPSED,
                notification_id=receipt,
            )


def _record(row) -> ReminderRecord:
    return ReminderRecord(
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
