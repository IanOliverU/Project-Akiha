"""Reminder clocks, timezone uncertainty, persistence and action authority."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import ActionRequest, build_default_action_registry
from project_akiha.core.actions.clarification import (
    ActionReadinessStatus,
    analyze_action_readiness,
)
from project_akiha.core.utilities.reminders import (
    AmbiguousReminderTime,
    NonexistentReminderTime,
    reminder_time,
)
from project_akiha.core.utilities.timers import TimerStatus
from project_akiha.database.migrator import DatabaseMigrator
from project_akiha.database.sqlite_notification_repository import (
    SQLiteNotificationRepository,
)
from project_akiha.database.sqlite_reminder_repository import SQLiteReminderRepository
from project_akiha.database.sqlite_timer_repository import SQLiteTimerRepository
from project_akiha.services.assistant_action_bridge import AssistantActionRequestParser
from project_akiha.services.timer_schedule import TimerScheduleService
from tests.unit.services.test_phase13c_timers import FakeClock


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class ReminderTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "schedules.sqlite3"
        self.clock = FakeClock()
        self.clock.wall = datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
        self.repo = SQLiteReminderRepository(self.path)
        self.owner = TimerScheduleService(
            SQLiteTimerRepository(self.path), self.clock, reminders=self.repo
        )

    def create(self, request="r-1", local="2026-10-09T08:01", label=""):
        return self.owner.create_reminder(
            request, digest(request), local, "Asia/Taipei", label
        )

    def test_explicit_timezone_and_exact_due_boundary(self):
        record = self.create()
        self.assertEqual(record.due_at, self.clock.wall + timedelta(seconds=60))
        self.clock.advance(59)
        self.assertEqual(self.owner.tick(), ())
        self.clock.advance(1)
        self.assertEqual(self.owner.tick()[0].reminder_id, record.reminder_id)
        self.assertEqual(self.owner.tick(), ())

    def test_timer_and_reminder_share_one_owner_and_tick(self):
        timer = self.owner.create("timer-req", digest("t"), 60)
        reminder = self.create()
        self.clock.advance(60)
        records = self.owner.tick()
        self.assertEqual(len(records), 2)
        self.assertEqual(
            {getattr(r, "timer_id", getattr(r, "reminder_id", None)) for r in records},
            {timer.timer_id, reminder.reminder_id},
        )

    def test_wall_clock_jump_affects_reminder_not_monotonic_timer(self):
        self.owner.create("timer-req", digest("t"), 60)
        reminder = self.create()
        self.clock.wall += timedelta(seconds=60)
        self.assertEqual(self.owner.tick()[0].reminder_id, reminder.reminder_id)
        self.assertEqual(len(self.owner.list()), 1)

    def test_cancel_prevents_delivery_and_snooze_cannot_revive(self):
        r = self.create()
        self.assertTrue(self.owner.cancel_reminder(r.reminder_id))
        self.assertFalse(self.owner.cancel_reminder(r.reminder_id))
        with self.assertRaises(ValueError):
            self.owner.snooze_reminder("s-1", digest("s"), r.reminder_id, 10)
        self.clock.advance(61)
        self.assertEqual(self.owner.tick(), ())

    def test_snooze_replay_never_moves_due_time(self):
        r = self.create()
        first = self.owner.snooze_reminder("s-1", digest("s"), r.reminder_id, 120)
        self.clock.advance(30)
        replay = self.owner.snooze_reminder("s-1", digest("s"), r.reminder_id, 120)
        self.assertEqual(first.due_at, replay.due_at)
        with self.assertRaises(ValueError):
            self.owner.snooze_reminder("s-1", digest("changed"), r.reminder_id, 60)

    def test_create_replay_and_changed_fingerprint(self):
        r = self.create()
        self.assertEqual(self.create(), r)
        with self.assertRaises(ValueError):
            self.owner.create_reminder(
                "r-1", digest("changed"), "2026-10-09T08:02", "Asia/Taipei"
            )

    def test_restart_atomic_receipt_and_sanitized_inbox(self):
        r = self.create(label="REMINDER_PRIVATE_SENTINEL")
        self.owner.close()
        self.clock.advance(60)
        restarted = TimerScheduleService(
            SQLiteTimerRepository(self.path), self.clock, reminders=self.repo
        )
        self.assertEqual(restarted.tick()[0].reminder_id, r.reminder_id)
        again = TimerScheduleService(
            SQLiteTimerRepository(self.path), self.clock, reminders=self.repo
        )
        self.assertEqual(again.tick(), ())
        rows = SQLiteNotificationRepository(self.path).list_recent()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].service.value, "reminders")
        self.assertNotIn("REMINDER_PRIVATE_SENTINEL", repr(rows))

    def test_missed_beyond_grace_is_inbox_only(self):
        self.create()
        self.clock.advance(3661)
        result = self.owner.tick()[0]
        self.assertIs(result.status, TimerStatus.MISSED)
        self.assertEqual(
            SQLiteNotificationRepository(self.path).list_recent()[0].status.value,
            "silent",
        )

    def test_exact_grace_boundary_still_delivers(self):
        self.create()
        self.clock.advance(3660)
        self.assertIs(self.owner.tick()[0].status, TimerStatus.ELAPSED)

    def test_parallel_claims_produce_one_receipt(self):
        r = self.create()
        self.clock.advance(60)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(
                    lambda _: self.repo.claim_expiry(
                        r.reminder_id, self.clock.wall, missed=False
                    ),
                    range(4),
                )
            )
        self.assertEqual(sum(x is not None for x in results), 1)

    def test_close_preserves_pending_and_stops_owner(self):
        r = self.create()
        self.owner.close()
        self.clock.advance(61)
        self.assertEqual(self.owner.tick(), ())
        self.assertEqual(self.repo.pending(), (r,))
        with self.assertRaises(RuntimeError):
            self.owner.list_reminders()

    def test_retention_redacts_terminal_labels_but_preserves_replay_and_receipts(self):
        timer = self.owner.create("retain-timer", digest("retain"), 1, "TIMER_PRIVATE")
        reminder = self.create(label="REMINDER_PRIVATE")
        self.clock.advance(60)
        self.owner.tick()
        self.clock.advance(31 * 86400)
        self.assertEqual(self.owner.redact_terminal_labels(30), 2)
        self.assertEqual(self.repo.get(reminder.reminder_id).label, "")
        self.assertEqual(self.owner.repository.get(timer.timer_id).label, "")
        self.assertEqual(len(SQLiteNotificationRepository(self.path).list_recent()), 2)
        replay = self.owner.create("retain-timer", digest("retain"), 1, "TIMER_PRIVATE")
        self.assertIs(replay.status, TimerStatus.ELAPSED)
        self.assertEqual(self.owner.tick(), ())

    def test_past_unbounded_and_invalid_label_fail_closed(self):
        for local, label in [
            ("2026-10-09T07:59", ""),
            ("2028-10-09T08:00", ""),
            ("2026-10-09T08:01", "private/path"),
        ]:
            with self.subTest(local=local), self.assertRaises(ValueError):
                self.create(local=local, label=label)
        self.assertEqual(self.repo.pending(), ())

    def test_migration_preserves_existing_timer_and_inbox_sequence(self):
        root = Path(self.temp.name)
        old = root / "old.sqlite3"
        scripts = root / "migrations"
        scripts.mkdir()
        source = Path(__file__).parents[3] / "project_akiha/database/migrations"
        for file in source.glob("*.sql"):
            if int(file.name.split("_")[0]) < 16:
                shutil.copyfile(file, scripts / file.name)
        DatabaseMigrator(old, scripts).apply_pending()
        with closing(sqlite3.connect(old)) as c, c:
            c.execute(
                "INSERT INTO "
                "notification_inbox(service,event_kind,priority,d"
                "isplay_text,occurred_at,created_at,delivery_stat"
                "us) VALUES "
                "('timers','timers.elapsed','normal','Existing "
                "timer','2026-10-09','2026-10-09','delivered')"
            )
            c.execute(
                "UPDATE sqlite_sequence SET seq=200 WHERE name='notification_inbox'"
            )
            c.execute(
                "INSERT INTO utility_timers VALUES (?,?,?,?,?,?,?,'pending',NULL,NULL)",
                (
                    "timer-" + "a" * 32,
                    "old-timer",
                    digest("old"),
                    "PRIVATE_SCHEDULE_LABEL",
                    60,
                    "2026-10-09T00:00:00+00:00",
                    "2026-10-09T00:01:00+00:00",
                ),
            )
            original = c.execute("SELECT * FROM utility_timers").fetchall()
            inbox = c.execute("SELECT * FROM notification_inbox").fetchall()
        script = source / "0016_one_shot_reminders.sql"
        target = scripts / script.name
        target.write_text(script.read_text() + "\nINVALID SQL;", encoding="utf-8")
        with (
            self.assertLogs("project_akiha.database.migrator", level="ERROR"),
            self.assertRaises(sqlite3.Error),
        ):
            DatabaseMigrator(old, scripts).apply_pending()
        with closing(sqlite3.connect(old)) as c:
            self.assertEqual(
                c.execute("SELECT max(version) FROM schema_version").fetchone()[0], 15
            )
            self.assertEqual(
                c.execute("SELECT * FROM notification_inbox").fetchall(), inbox
            )
        shutil.copyfile(script, target)
        DatabaseMigrator(old, scripts).apply_pending()
        with closing(sqlite3.connect(old)) as c:
            self.assertEqual(
                c.execute("SELECT * FROM utility_timers").fetchall(), original
            )
            self.assertEqual(
                c.execute("SELECT * FROM notification_inbox").fetchall(), inbox
            )
            self.assertEqual(
                c.execute(
                    "SELECT seq FROM sqlite_sequence WHERE name='notification_inbox'"
                ).fetchone()[0],
                200,
            )


class ReminderTimezoneAndRoutingTest(unittest.TestCase):
    def test_dst_repeated_time_requires_explicit_occurrence(self):
        with self.assertRaises(AmbiguousReminderTime):
            reminder_time("2026-11-01T01:30", "America/New_York")
        first = reminder_time("2026-11-01T01:30", "America/New_York", 0)
        second = reminder_time("2026-11-01T01:30", "America/New_York", 1)
        self.assertEqual((second - first).total_seconds(), 3600)

    def test_dst_skipped_time_requires_another_time(self):
        with self.assertRaises(NonexistentReminderTime):
            reminder_time("2026-03-08T02:30", "America/New_York")

    def test_dst_readiness_uses_existing_local_clarification(self):
        for date, missing in [
            ("2026-11-01T01:30", "fold"),
            ("2026-03-08T02:30", "local_time"),
        ]:
            request = ActionRequest(
                "dst-check",
                "reminders.create",
                "chat",
                {
                    "service": "reminders",
                    "local_time": date,
                    "timezone": "America/New_York",
                },
            )
            decision = analyze_action_readiness(
                request, build_default_action_registry()
            )
            self.assertIs(decision.status, ActionReadinessStatus.CLARIFICATION_REQUIRED)
            self.assertEqual(decision.spec.missing_parameters, (missing,))

    def test_invalid_date_zone_offset_and_fold_rejected(self):
        for date, zone, fold in [
            ("tomorrow", "UTC", None),
            ("2026-10-09T08:00", "Unknown/Zone", None),
            ("2026-10-09T08:00+08:00", "UTC", None),
            ("2026-10-09T08:00", "UTC", True),
        ]:
            with self.subTest(date=date), self.assertRaises(ValueError):
                reminder_time(date, zone, fold)

    def test_bounded_commands_and_courtesy_envelope(self):
        parser = AssistantActionRequestParser()
        for text in [
            "Set a reminder at 2026-10-09 08:01 Asia/Taipei named tea",
            "Akiha, please set a reminder at 2026-10-09 08:01 Asia/Taipei named tea",
        ]:
            request = parser.parse(text, correlation_id="parse-reminder")
            self.assertEqual(request.action_id, "reminders.create")
            self.assertEqual(request.parameters["timezone"], "Asia/Taipei")
