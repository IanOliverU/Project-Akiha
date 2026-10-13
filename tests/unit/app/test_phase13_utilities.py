"""Connected utility controls, transient weather and confirmed selected exports."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from contextlib import closing
from datetime import UTC, datetime
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from project_akiha.core.actions import ActionStatus
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.core.utilities.information import WeatherSnapshot
from project_akiha.services.transcript_export import render_chat_transcript
from tests.unit.app import test_phase13b_composition as composition
from tests.unit.app import test_phase13c_timers as timers


class UtilitiesCompositionTest(unittest.TestCase):
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
        self.settings = self.state["settings_window"]
        self.panel = self.settings._utilities_panel

    def privacy_surfaces(self):
        self.send("I prefer public coffee with oat milk.")
        memories = asyncio.run(self.state["memory_repository"].get_recent_memories(100))
        self.assertTrue(memories)
        exported = render_chat_transcript(
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
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        return (
            repr(tables)
            + repr(memories)
            + exported
            + repr(provider)
            + repr(self.events)
            + logs
            + self.window._history_view.toPlainText()
        )

    def test_weather_transient_local_display_excluded_from_connected_storage(self):
        self.panel._weather_enabled.setChecked(True)
        self.panel._location_configured.setChecked(True)
        self.panel._latitude.setValue(25.12345)
        self.panel._longitude.setValue(121.54321)
        self.settings._save()
        secret = "WEATHER_PRIVATE_SENTINEL"
        snapshot = WeatherSnapshot(
            "Synthetic weather",
            datetime(2026, 10, 9, tzinfo=UTC),
            datetime(2026, 10, 9, tzinfo=UTC),
            21,
            4,
            0,
            (),
            (secret,),
            "Synthetic alert fixture",
        )
        with patch(
            "project_akiha.services.current_information.OpenMeteoInformationProvider.fetch",
            return_value=snapshot,
        ):
            self.send("Weather")
            self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.assertIn(secret, self.panel._weather.text())
        self.assertNotIn(secret, self.privacy_surfaces())
        health = self.state["provider_health_registry"].snapshot()
        self.assertNotIn(secret, repr(health))
        self.assertNotIn("25.12345", repr(health))

    def test_disabled_weather_and_specific_url_never_fetch_provider(self):
        with patch(
            "project_akiha.services.current_information.OpenMeteoInformationProvider.fetch"
        ) as fetch:
            self.send("Weather")
            self.assertIs(self.dispatch().result.status, ActionStatus.UNAVAILABLE)
            fetch.assert_not_called()
        self.assertIn("Configure", self.panel._weather.text())
        self.send("I prefer public coffee.")
        self.assertTrue(self.chat.messages)

    def test_settings_timer_request_uses_existing_validation_and_owner(self):
        self.panel._seconds.setValue(10)
        self.panel._label.setText("LOCAL_SETTINGS_PRIVATE")
        self.panel._create_timer()
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        record = self.service.list()[0]
        self.state["refresh_utility_schedules"]()
        self.assertIn("LOCAL_SETTINGS_PRIVATE", self.panel._schedules.item(0).text())
        self.panel._schedules.setCurrentRow(0)
        self.panel._cancel()
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.assertEqual(self.service.list(), ())
        self.assertNotIn(record.label, self.window._history_view.toPlainText())

    def test_confirmed_export_opaque_token_and_no_destination_or_data_in_audit(self):
        self.send("I prefer public coffee with oat milk.")
        exporter = self.state["user_export_service"]
        selection = exporter.catalog("conversations")
        self.assertTrue(selection)
        destination = self.root / "DESTINATION_PRIVATE_SENTINEL.json"
        request = exporter.prepare("conversations", (selection[0][0],), destination)
        self.assertNotIn(str(destination), repr(request))
        self.state["start_action_thread"](request)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            self.assertIs(
                self.dispatch().result.status, ActionStatus.CONFIRMATION_REQUIRED
            )
        self.assertIs(self.dispatch().result.status, ActionStatus.SUCCESS)
        self.assertTrue(destination.exists())
        self.assertIn("coffee", destination.read_text(encoding="utf-8"))
        self.assertNotIn("DESTINATION_PRIVATE_SENTINEL", self.privacy_surfaces())

    def test_shutdown_invalidates_pending_clarification(self):
        self.send("Open a folder")
        identity = self.leases.pending.identity
        self.state["shutdown_app"]()
        self.assertIsNone(self.leases.pending)
        result = self.controller.resolve(
            ClarificationAnswer(
                identity, ClarificationAnswerSource.LOCAL_UI, "private local answer"
            )
        )
        self.assertIs(result.outcome, ClarificationOutcome.STALE)

    def test_cancelled_export_creates_no_file(self):
        self.send("A public conversational fixture.")
        exporter = self.state["user_export_service"]
        identifier = exporter.catalog("conversations")[0][0]
        destination = self.root / "cancelled.json"
        request = exporter.prepare("conversations", (identifier,), destination)
        self.state["start_action_thread"](request)
        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ):
            self.dispatch()
        self.assertFalse(destination.exists())
        self.assertEqual(exporter._drafts, {})
