"""Timer commands through the real composed application and SQLite action audit."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from contextlib import closing

from project_akiha.core.actions import ActionRequest, ActionStatus
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
)
from project_akiha.services.transcript_export import render_chat_transcript
from tests.unit.app import test_phase13b_composition as composition
from tests.unit.app import test_phase13b_usability as usability
from tests.unit.services.test_phase13c_timers import FakeClock


class TimerCompositionTest(unittest.TestCase):
    release_graph = composition.Phase13BCompositionTest.release_graph
    send = composition.Phase13BCompositionTest.send
    wait_chat = composition.Phase13BCompositionTest.wait_chat
    voice = usability.Phase13BUsabilityTest.voice

    @classmethod
    def setUpClass(cls):
        composition.Phase13BCompositionTest.setUpClass()
        cls.app = composition.Phase13BCompositionTest.app

    def setUp(self):
        composition.Phase13BCompositionTest.setUp(self)
        self.state["utility_timer_tick"].stop()
        self.service = self.state["timer_schedule_service"]
        self.clock = FakeClock()
        self.service.clock = self.clock

    def dispatch(self):
        worker = composition._ControlledAction.created[-1]
        result = asyncio.run(worker._dispatch())
        worker.result_ready.emit(result)
        worker.finished.emit()
        self.window.set_busy(False)
        return result

    def test_typed_and_local_voice_share_real_timer_executor_without_provider(self):
        self.send("Akiha, please set a timer for 5 minutes named tea")
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.voice("Set a timer for 5 minutes named tea")
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(self.service.list()), 2)
        self.assertEqual(self.provider.prompts, [])

    def test_real_action_audit_and_inbox_receive_one_expiry_and_cancel_prevents_other(
        self,
    ):
        self.send("Set a timer for 3 seconds")
        self.dispatch()
        first = self.service.list()[0]
        self.send("Set a timer for 3 seconds")
        self.dispatch()
        second = next(r for r in self.service.list() if r.timer_id != first.timer_id)
        self.send(f"Cancel timer {second.timer_id}")
        self.dispatch()
        self.clock.advance(3)
        self.state["timer_delivery_controller"].tick()
        self.state["timer_delivery_controller"].tick()
        self.assertEqual(len(self.state["notification_repository"].list_recent()), 1)
        audits = asyncio.run(
            self.state["action_repository"].get_recent_action_audits(limit=10)
        )
        self.assertEqual(len(audits), 3)
        self.assertTrue(all(a.normalized_target == "timers" for a in audits))

    def test_missing_duration_opaque_lease_selection_is_superseded_and_expired(self):
        self.send("Set a timer")
        identity = self.leases.pending.identity
        self.send("Open an app")
        outcome = self.controller.resolve(
            ClarificationAnswer(identity, ClarificationAnswerSource.LOCAL_UI, "10")
        )
        self.assertIsNone(outcome.request)
        self.assertEqual(self.service.list(), ())
        self.send("Set a timer")
        self.leases.clock = self.clock
        # Captured system-monotonic deadline: move the fake clock to exact expiry.
        identity = self.leases.pending.identity
        self.clock.mono = identity.deadline
        outcome = self.controller.resolve(
            ClarificationAnswer(identity, ClarificationAnswerSource.LOCAL_UI, "10")
        )
        self.assertIsNone(outcome.request)
        self.assertEqual(self.service.list(), ())

    def test_invalid_and_provider_timer_requests_cannot_create_rows(self):
        self.send("Set a timer for 1.5 minutes")
        self.dispatch()
        request = ActionRequest(
            "forged-timer",
            "timers.create",
            "provider.gemini",
            {"service": "timers", "duration_seconds": 10},
        )
        result = asyncio.run(
            self.state["assistant_action_service"].evaluate_request(request)
        )
        self.assertIs(result.status, ActionStatus.DENIED)
        self.assertEqual(self.service.list(), ())

    def test_timer_label_stays_in_schedule_not_provider_chat_memory_export_or_logs(
        self,
    ):
        sentinel = "TIMER_PRIVATE_LABEL_SENTINEL"
        self.send(f"Set a timer for 2 seconds named {sentinel}")
        self.dispatch()
        self.clock.advance(2)
        self.state["timer_delivery_controller"].tick()
        self.send("I prefer public coffee with oat milk.")
        memories = asyncio.run(self.state["memory_repository"].get_recent_memories(100))
        self.assertTrue(memories)
        export = render_chat_transcript(
            asyncio.run(self.chat.get_export_messages()), assistant_name="Akiha"
        )
        provider = asyncio.run(self.chat.build_provider_messages("public followup"))
        asyncio.run(self.chat.start_new_conversation())
        with closing(sqlite3.connect(self.state["paths"].database_path)) as c:
            tables = {
                name: c.execute('SELECT * FROM "' + name + '"').fetchall()
                for (name,) in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertIn(sentinel, repr(tables.pop("utility_timers")))
        self.assertIn("coffee", repr(tables["conversations"]))
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        self.assertNotIn(
            sentinel,
            repr(tables)
            + repr(memories)
            + repr(provider)
            + export
            + repr(self.events)
            + logs
            + self.window._history_view.toPlainText(),
        )

    def test_main_shutdown_stops_timer_tick_and_preserves_recovery_metadata(self):
        self.send("Set a timer for 10 seconds")
        self.dispatch()
        pending = self.service.list()
        self.state["shutdown_app"]()
        self.assertFalse(self.state["utility_timer_tick"].isActive())
        self.assertEqual(self.service.tick(), ())
        self.assertEqual(self.service.repository.pending(), pending)
