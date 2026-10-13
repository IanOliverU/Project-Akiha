"""Reminder parsing, leases and privacy through the actual application graph."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from contextlib import closing

from project_akiha.core.actions import ActionStatus
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.services.transcript_export import render_chat_transcript
from tests.unit.app import test_phase13b_composition as composition
from tests.unit.app import test_phase13c_timers as timers


class ReminderCompositionTest(unittest.TestCase):
    release_graph = timers.TimerCompositionTest.release_graph
    send = timers.TimerCompositionTest.send
    wait_chat = timers.TimerCompositionTest.wait_chat
    voice = timers.TimerCompositionTest.voice
    dispatch = timers.TimerCompositionTest.dispatch

    @classmethod
    def setUpClass(cls):
        composition.Phase13BCompositionTest.setUpClass()
        cls.app = composition.Phase13BCompositionTest.app

    def setUp(self):
        timers.TimerCompositionTest.setUp(self)
        self.panel = self.state["clarification_panel"]

    def test_typed_and_local_voice_share_owner(self):
        self.send("Akiha, please set a reminder at 2026-10-08 12:01 UTC named tea")
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.voice("Set a reminder at 2026-10-08 12:02 UTC named tea")
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(self.service.list_reminders()), 2)
        self.assertEqual(self.provider.prompts, [])
        self.assertNotIn("named tea", self.window._history_view.toPlainText())

    def test_missing_date_timezone_and_dst_use_real_panel(self):
        self.send("Set a reminder")
        self.panel._answer.setText("2026-10-08T12:01")
        self.panel._submit.click()
        self.assertEqual(self.leases.pending.spec.missing_parameters, ("timezone",))
        self.panel._answer.setText("UTC")
        self.panel._submit.click()
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.send("Set a reminder at 2026-11-01 01:30 America/New_York")
        self.assertEqual(self.leases.pending.spec.missing_parameters, ("fold",))
        self.panel._answer.setText("1")
        self.panel._submit.click()
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)

    def test_superseded_reminder_answer_cannot_create_schedule(self):
        self.send("Set a reminder")
        identity = self.leases.pending.identity
        self.send("Open an app")
        result = self.controller.resolve(
            ClarificationAnswer(
                identity, ClarificationAnswerSource.LOCAL_UI, "2026-10-08T12:01"
            )
        )
        self.assertIs(result.outcome, ClarificationOutcome.STALE)
        self.assertEqual(self.service.list_reminders(), ())

    def test_private_label_only_persists_in_schedule_metadata(self):
        secret = "REMINDER_PRIVATE_SENTINEL"
        self.send(f"Set a reminder at 2026-10-08 12:01 UTC named {secret}")
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.clock.advance(60)
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
        self.assertIn(secret, repr(tables.pop("utility_reminders")))
        self.assertIn("coffee", repr(tables["conversations"]))
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        self.assertNotIn(
            secret,
            repr(tables)
            + repr(memories)
            + export
            + repr(provider)
            + repr(self.events)
            + logs
            + self.window._history_view.toPlainText(),
        )
