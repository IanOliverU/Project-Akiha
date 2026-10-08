"""Adversarial timer lifecycle, persistence, delivery and authority checks."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import Mock, patch

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.app.proactive_speech_controller import ProactiveSpeechController
from project_akiha.app.timer_delivery_controller import TimerDeliveryController
from project_akiha.config import BehaviorConfig, ExternalIntegrationsConfig
from project_akiha.core.actions import (
    ActionPermissionPolicy,
    ActionRequestValidator,
    ActionValidationError,
    PermissionDecision,
    ProtectedPathPolicy,
    build_default_action_registry,
    build_default_provider_action_catalog,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ProactiveDeliveryService,
)
from project_akiha.core.events import EventBus, EventType
from project_akiha.core.notifications import NotificationInboxStatus
from project_akiha.core.utilities.timers import (
    MAX_TIMER_SECONDS,
    TIMER_ACTIONS,
    TIMER_RECOVERY_GRACE_SECONDS,
    TimerStatus,
    validate_timer_input,
)
from project_akiha.database.migrator import DatabaseMigrator
from project_akiha.database.sqlite_notification_repository import (
    SQLiteNotificationRepository,
)
from project_akiha.database.sqlite_timer_repository import SQLiteTimerRepository
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.assistant_action_bridge import AssistantActionRequestParser
from project_akiha.services.timer_schedule import TimerScheduleService


class FakeClock:
    def __init__(self):
        self.wall = datetime(2026, 10, 8, 12, tzinfo=UTC)
        self.mono = 100.0

    def now_utc(self):
        return self.wall

    def monotonic_seconds(self):
        return self.mono

    def advance(self, seconds):
        self.wall += timedelta(seconds=seconds)
        self.mono += seconds


class TimerLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "timers.sqlite3"
        self.repo = SQLiteTimerRepository(self.path)
        self.clock = FakeClock()
        self.service = TimerScheduleService(self.repo, self.clock)
        self.inbox = SQLiteNotificationRepository(self.path)

    def create(self, request="one", seconds=10, label=""):
        digest = hashlib.sha256(f"{request}:{seconds}:{label}".encode()).hexdigest()
        return self.service.create(request, digest, seconds, label)

    def test_exact_monotonic_expiry_and_single_inbox_receipt(self):
        timer = self.create()
        self.clock.advance(9.999)
        self.assertEqual(self.service.tick(), ())
        self.clock.advance(0.001)
        result = self.service.tick()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].timer_id, timer.timer_id)
        self.assertEqual(self.service.tick(), ())
        self.assertEqual(len(self.inbox.list_recent()), 1)

    def test_forward_and_backward_wall_jumps_do_not_change_running_deadline(self):
        self.create()
        for change in (86400, -172800):
            self.clock.wall += timedelta(seconds=change)
            self.assertEqual(self.service.tick(), ())
        self.clock.mono += 10
        self.assertEqual(len(self.service.tick()), 1)

    def test_simultaneous_timers_all_fire_once(self):
        expected = {self.create(str(i)).timer_id for i in range(5)}
        self.clock.advance(10)
        self.assertEqual({r.timer_id for r in self.service.tick()}, expected)
        self.assertEqual(len(self.inbox.list_recent()), 5)

    def test_cancel_before_due_prevents_delivery_and_is_idempotent(self):
        timer = self.create()
        self.assertTrue(self.service.cancel(timer.timer_id))
        self.assertFalse(self.service.cancel(timer.timer_id))
        self.clock.advance(10)
        self.assertEqual(self.service.tick(), ())
        self.assertEqual(self.inbox.list_recent(), ())

    def test_cancel_after_expiry_does_not_remove_receipt(self):
        timer = self.create()
        self.clock.advance(10)
        self.service.tick()
        self.assertFalse(self.service.cancel(timer.timer_id))
        self.assertEqual(len(self.inbox.list_recent()), 1)

    def test_cancel_racing_tick_has_one_terminal_state(self):
        timer = self.create()
        self.clock.advance(10)
        barrier = Barrier(2)

        def cancel():
            barrier.wait()
            return self.service.cancel(timer.timer_id)

        def tick():
            barrier.wait()
            return self.service.tick()

        with ThreadPoolExecutor(2) as pool:
            a, b = pool.submit(cancel), pool.submit(tick)
            cancelled, delivered = a.result(), b.result()
        self.assertEqual(int(cancelled) + len(delivered), 1)
        self.assertEqual(len(self.inbox.list_recent()), len(delivered))

    def test_two_service_instances_cannot_claim_two_inbox_entries(self):
        self.create()
        other = TimerScheduleService(self.repo, self.clock)
        self.clock.advance(10)
        with ThreadPoolExecutor(2) as pool:
            a, b = pool.submit(self.service.tick), pool.submit(other.tick)
            self.assertEqual(len(a.result()) + len(b.result()), 1)
        self.assertEqual(len(self.inbox.list_recent()), 1)

    def test_same_request_replay_retains_id_and_original_deadline(self):
        first = self.create()
        self.clock.advance(5)
        self.assertEqual(self.create(), first)
        self.clock.advance(5)
        self.assertEqual(len(self.service.tick()), 1)
        self.assertIs(self.create().status, TimerStatus.ELAPSED)
        self.assertEqual(self.service.tick(), ())

    def test_changed_request_fingerprint_fails_without_new_timer(self):
        self.create()
        with self.assertRaises(ValueError):
            self.create(seconds=11)
        self.assertEqual(len(self.service.list()), 1)

    def test_active_capacity_is_transactional_and_cancellation_frees_slot(self):
        timers = [self.create(str(i)) for i in range(100)]
        with self.assertRaises(ValueError):
            self.create("overflow")
        self.service.cancel(timers[0].timer_id)
        self.create("replacement")
        self.assertEqual(len(self.service.list()), 100)

    def test_duration_and_label_bounds_fail_closed(self):
        for seconds in (0, -1, True, 1.5, MAX_TIMER_SECONDS + 1):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                validate_timer_input(seconds, "")
        for label in ("x" * 65, "private/path", "file:///private", "x\nsecret"):
            with self.subTest(label=label), self.assertRaises(ValueError):
                validate_timer_input(10, label)
        self.create(seconds=MAX_TIMER_SECONDS, label="tea break")

    def test_shutdown_preserves_pending_and_refuses_new_actions(self):
        timer = self.create()
        self.service.close()
        self.clock.advance(5)
        self.assertEqual(self.service.tick(), ())
        with self.assertRaises(RuntimeError):
            self.create("closed")
        restarted = TimerScheduleService(self.repo, self.clock)
        self.assertEqual(restarted.inspect(timer.timer_id)[1], 5)
        self.clock.advance(5)
        self.assertEqual(len(restarted.tick()), 1)

    def test_restart_after_durable_receipt_never_redelivers(self):
        self.create()
        self.clock.advance(10)
        self.service.tick()
        # Simulate a crash before UI delivery: only durable inbox survives.
        restarted = TimerScheduleService(self.repo, self.clock)
        self.assertEqual(restarted.tick(), ())
        self.assertEqual(len(self.inbox.list_recent()), 1)

    def test_recent_overdue_restart_delivers_once_at_grace_boundary(self):
        self.create()
        self.clock.advance(10 + TIMER_RECOVERY_GRACE_SECONDS)
        restarted = TimerScheduleService(self.repo, self.clock)
        self.assertIs(restarted.tick()[0].status, TimerStatus.ELAPSED)

    def test_old_overdue_restart_is_silent_missed_inbox_entry(self):
        self.create()
        self.clock.advance(11 + TIMER_RECOVERY_GRACE_SECONDS)
        restarted = TimerScheduleService(self.repo, self.clock)
        self.assertIs(restarted.tick()[0].status, TimerStatus.MISSED)
        self.assertIs(
            self.inbox.list_recent()[0].status, NotificationInboxStatus.SILENT
        )

    def test_backward_wall_jump_on_restart_cannot_extend_original_duration(self):
        timer = self.create()
        self.clock.wall -= timedelta(days=10)
        self.assertEqual(
            TimerScheduleService(self.repo, self.clock).inspect(timer.timer_id)[1], 10
        )

    def test_expiry_transaction_rolls_back_inbox_if_receipt_update_fails(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute(
                "CREATE TRIGGER block_receipt BEFORE UPDATE ON utility_timers "
                "BEGIN SELECT RAISE(ABORT,'blocked'); END"
            )
        self.clock.advance(10)
        with self.assertRaises(sqlite3.Error):
            self.service.tick()
        self.assertEqual(self.inbox.list_recent(), ())
        self.assertEqual(len(self.service.list()), 1)
        with closing(sqlite3.connect(self.path)) as c, c:
            c.execute("DROP TRIGGER block_receipt")
        self.assertEqual(len(self.service.tick()), 1)

    def test_database_error_does_not_leak_exception_or_claim_success(self):
        with patch.object(
            self.repo, "claim_expiry", side_effect=OSError("PRIVATE_SECRET")
        ):
            self.create()
            self.clock.advance(10)
            controller = self.delivery_controller()
            with self.assertLogs("project_akiha.timers", level="ERROR") as logs:
                controller.tick()
            self.assertNotIn("PRIVATE_SECRET", repr(logs.output))
        self.assertEqual(self.inbox.list_recent(), ())
        controller.tick()
        self.assertEqual(len(self.inbox.list_recent()), 1)

    def delivery_controller(self, behavior=None, prefs=None, busy=False):
        self.surface = Mock()
        self.surface.is_chat_visible.return_value = True
        self.surface.can_show_tray_message.return_value = True
        self.bus = EventBus()
        self.events = []
        self.bus.subscribe(EventType.PROACTIVE_SUGGESTION_DELIVERED, self.events.append)
        return TimerDeliveryController(
            self.service,
            inbox=self.inbox,
            notification_policy=NotificationPolicy(behavior or BehaviorConfig()),
            activity_provider=lambda: ActivitySnapshot(
                ActivityState.ACTIVE, 0, self.clock.wall, "test"
            ),
            delivery_controller=ProactiveDeliveryController(
                self.bus, ProactiveDeliveryService(), self.surface
            ),
            preference_provider=lambda: prefs or ExternalIntegrationsConfig(),
            busy_provider=lambda: busy,
            now_provider=self.clock.now_utc,
        )

    def test_delivery_uses_existing_surface_and_never_exposes_label(self):
        controller = self.delivery_controller()
        self.create(label="PRIVATE_LABEL_SENTINEL")
        self.clock.advance(10)
        controller.tick()
        self.surface.append_chat_suggestion.assert_called_once()
        self.assertIs(
            self.inbox.list_recent()[0].status, NotificationInboxStatus.DELIVERED
        )
        self.assertNotIn(
            "PRIVATE_LABEL_SENTINEL", repr(self.events) + repr(self.inbox.list_recent())
        )

    def test_quiet_hours_suppress_channels_but_retain_inbox(self):
        controller = self.delivery_controller(
            behavior=replace(
                BehaviorConfig(),
                quiet_hours_enabled=True,
                quiet_hours_start="00:00",
                quiet_hours_end="23:59",
            )
        )
        self.create()
        self.clock.advance(10)
        controller.tick()
        self.surface.append_chat_suggestion.assert_not_called()
        self.assertIs(
            self.inbox.list_recent()[0].status, NotificationInboxStatus.SUPPRESSED
        )

    def test_busy_presentation_suppresses_expiry_without_retry(self):
        controller = self.delivery_controller(busy=True)
        self.create()
        self.clock.advance(10)
        controller.tick()
        self.surface.append_chat_suggestion.assert_not_called()
        self.assertEqual(self.events, [])
        controller.busy = lambda: False
        controller.tick()
        self.assertEqual(self.events, [])

    def test_channel_preferences_and_voice_opt_out_are_preserved(self):
        controller = self.delivery_controller(
            prefs=replace(
                ExternalIntegrationsConfig(),
                chat_notifications_enabled=False,
                voice_notifications_enabled=False,
            )
        )
        self.create()
        self.clock.advance(10)
        controller.tick()
        self.surface.append_chat_suggestion.assert_not_called()
        self.surface.show_tray_message.assert_called_once()
        self.assertIs(self.events[0].payload["speech_enabled"], False)

    def test_real_proactive_speech_route_obeys_voice_preference(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                controller = self.delivery_controller(
                    prefs=replace(
                        ExternalIntegrationsConfig(),
                        voice_notifications_enabled=enabled,
                    )
                )
                speech = Mock()
                ProactiveSpeechController(self.bus, speech)
                self.create(request=f"voice-{enabled}")
                self.clock.advance(10)
                controller.tick()
                self.assertEqual(
                    speech.submit_proactive_suggestion.call_count, int(enabled)
                )
                if enabled:
                    line = speech.submit_proactive_suggestion.call_args.args[0]
                    self.assertTrue(line)
                    self.assertNotIn("timer-", line)

    def test_all_visual_channels_disabled_retains_silent_inbox(self):
        controller = self.delivery_controller(
            prefs=replace(
                ExternalIntegrationsConfig(),
                chat_notifications_enabled=False,
                visual_notifications_enabled=False,
            )
        )
        self.create()
        self.clock.advance(10)
        controller.tick()
        self.assertIs(
            self.inbox.list_recent()[0].status, NotificationInboxStatus.SILENT
        )

    def test_presentation_failure_never_replays_receipt(self):
        controller = self.delivery_controller()
        self.surface.append_chat_suggestion.side_effect = RuntimeError("PRIVATE_SECRET")
        self.create()
        self.clock.advance(10)
        with self.assertLogs("project_akiha.timers", level="ERROR") as logs:
            controller.tick()
        self.assertNotIn("PRIVATE_SECRET", repr(logs.output))
        controller.tick()
        self.surface.append_chat_suggestion.assert_called_once()
        self.assertEqual(len(self.inbox.list_recent()), 1)


class TimerBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.parser = AssistantActionRequestParser()
        self.validator = ActionRequestValidator(
            build_default_action_registry(), ProtectedPathPolicy()
        )

    def test_supported_units_and_politeness_are_bounded(self):
        for command, seconds in (
            ("Set a timer for 5 minutes", 300),
            ("Akiha, please start a timer for 2 hours.", 7200),
            ("/timer 3 seconds named tea", 3),
        ):
            with self.subTest(command=command):
                request = self.parser.parse(command)
                self.assertEqual(request.parameters["duration_seconds"], seconds)
                self.validator.validate(request)

    def test_invalid_fractional_uncertain_compound_requests_do_not_execute_prefix(
        self,
    ):
        for command in (
            "Set a timer for 1.5 minutes",
            "Set a timer for a while",
            "Set a timer for 0 seconds",
            "Set a timer for 9999999 hours",
            "Set a timer for 5 minutes and open Spotify",
            "Set a timer for 5 minutes named tea and open Spotify",
        ):
            with (
                self.subTest(command=command),
                self.assertRaises(ActionValidationError),
            ):
                self.validator.validate(self.parser.parse(command))

    def test_negation_metalinguistic_and_ordinary_chat_do_not_create_timers(self):
        for command in (
            "Do not set a timer for 3 minutes",
            "Do not cancel timer abc",
            "How do I set a timer?",
            "I like timers",
            "The command set a timer is useful",
        ):
            self.assertIsNone(self.parser.parse(command))

    def test_list_inspect_cancel_and_missing_targets(self):
        timer_id = "timer-" + "a" * 32
        for command, action in (
            ("List timers", "timers.list"),
            (f"Inspect timer {timer_id}", "timers.inspect"),
            (f"/timer cancel {timer_id}", "timers.cancel"),
        ):
            request = self.parser.parse(command)
            self.assertEqual(request.action_id, action)
            self.validator.validate(request)
        self.assertNotIn(
            "duration_seconds", self.parser.parse("Set a timer").parameters
        )
        self.assertNotIn("timer_id", self.parser.parse("Cancel timer").parameters)

    def test_provider_catalog_excludes_timers_and_source_cannot_bypass_policy(self):
        catalog = build_default_provider_action_catalog()
        for action_id in TIMER_ACTIONS:
            with self.assertRaises(ActionValidationError):
                catalog.resolve(action_id)
        local = self.validator.validate(self.parser.parse("Set a timer for 3 seconds"))
        policy = ActionPermissionPolicy(ProtectedPathPolicy())
        self.assertIs(policy.evaluate(local, ()), PermissionDecision.GRANTED)
        forged = replace(
            local, request=replace(local.request, source="provider.gemini")
        )
        self.assertIs(policy.evaluate(forged, ()), PermissionDecision.MISSING)

    def test_missing_duration_uses_original_lease_and_expiry(self):
        clock = FakeClock()
        leases = ActionClarificationService(clock=clock)
        controller = ActionClarificationController(leases)
        request = self.parser.parse("Set a timer", correlation_id="incomplete")
        self.assertFalse(controller.prepare(request))
        identity = leases.pending.identity
        result = controller.resolve(
            ClarificationAnswer(identity, ClarificationAnswerSource.LOCAL_UI, "12")
        )
        self.assertIs(result.outcome, ClarificationOutcome.RESOLVED)
        self.assertEqual(result.request.correlation_id, request.correlation_id)
        self.assertEqual(result.request.parameters["duration_seconds"], 12)
        self.assertIs(
            controller.resolve(
                ClarificationAnswer(identity, ClarificationAnswerSource.LOCAL_UI, "12")
            ).outcome,
            ClarificationOutcome.STALE,
        )


class TimerMigrationTest(unittest.TestCase):
    def test_upgrade_preserves_notification_data_and_rollback_on_failure(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            migrations = root / "migrations"
            migrations.mkdir()
            source = Path(__file__).parents[3] / "project_akiha/database/migrations"
            for file in source.glob("*.sql"):
                if not file.name.startswith("0015_"):
                    shutil.copyfile(file, migrations / file.name)
            db = root / "old.sqlite3"
            migrator = DatabaseMigrator(db, migrations)
            migrator.apply_pending()
            with closing(sqlite3.connect(db)) as c, c:
                c.execute(
                    "INSERT INTO notification_inbox(service,event_kind,priority,"
                    "display_text,occurred_at,created_at,read_at,delivery_status) "
                    "VALUES ('gmail','gmail.new_message','normal','existing notice',"
                    "'2026-10-08','2026-10-08','2026-10-08','delivered')"
                )
                old = c.execute("SELECT * FROM notification_inbox").fetchall()
                c.execute(
                    "UPDATE sqlite_sequence SET seq=200 WHERE name='notification_inbox'"
                )
            script = source / "0015_one_shot_timers.sql"
            target = migrations / script.name
            target.write_text(script.read_text() + "\nINVALID SQL;", encoding="utf-8")
            with (
                self.assertLogs("project_akiha.database.migrator", level="ERROR"),
                self.assertRaises(sqlite3.Error),
            ):
                migrator.apply_pending()
            with closing(sqlite3.connect(db)) as c:
                self.assertEqual(
                    c.execute("SELECT * FROM notification_inbox").fetchall(), old
                )
                self.assertEqual(
                    c.execute("SELECT max(version) FROM schema_version").fetchone()[0],
                    14,
                )
            shutil.copyfile(script, target)
            migrator.apply_pending()
            migrator.apply_pending()
            with closing(sqlite3.connect(db)) as c:
                self.assertEqual(
                    c.execute("SELECT * FROM notification_inbox").fetchall(), old
                )
                self.assertEqual(
                    c.execute("SELECT max(version) FROM schema_version").fetchone()[0],
                    15,
                )
                self.assertEqual(
                    c.execute("SELECT count(*) FROM utility_timers").fetchone()[0], 0
                )
                self.assertEqual(
                    c.execute(
                        "SELECT seq FROM sqlite_sequence "
                        "WHERE name='notification_inbox'"
                    ).fetchone()[0],
                    200,
                )
