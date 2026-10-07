"""Listening-history privacy and routing in the complete production app graph."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from project_akiha.config import SpotifyConfig
from project_akiha.core.actions import ActionExecutionResult, ActionStatus
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.integrations.spotify.auth import SpotifyToken
from project_akiha.integrations.spotify.history import (
    HistoryStatus,
    SpotifyHistorySnapshot,
    fetch_spotify_history,
)
from project_akiha.services.transcript_export import render_chat_transcript
from tests.unit.app import test_phase13b_composition as composition
from tests.unit.app import test_phase13b_usability as usability
from tests.unit.integrations.spotify.test_history import play
from tests.unit.integrations.spotify.test_session import _SecretStore


class SpotifyHistoryCompositionTest(unittest.TestCase):
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
        self.panel = self.state["clarification_panel"]
        self.session = self.state["spotify_session"]
        self.client = self.state["spotify_client"]
        self.state["apply_settings"](
            replace(
                self.state["config"],
                spotify=SpotifyConfig(enabled=True, client_id="a" * 32),
            )
        )
        self.session._secret_store = _SecretStore("synthetic-refresh")
        self.session._token_refresher = lambda *_: SpotifyToken(
            "synthetic-access",
            "synthetic-refresh",
            10**12,
            ("user-read-recently-played",),
        )
        asyncio.run(self.state["assistant_permission_service"].grant_spotify_playback())
        self.calls = []

        def transport(url, *_):
            self.calls.append(url)
            return {
                "items": [
                    play("one", title="HISTORY_PRIVATE_SENTINEL"),
                    play("one"),
                    play("two"),
                ]
            }

        self.client._transport = transport
        patcher = patch.object(
            composition.main, "SpotifyHistoryThread", composition._ControlledSearch
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def deliver(self):
        snapshot = fetch_spotify_history(
            self.client, self.session, self.session.generation
        )
        thread = composition._ControlledSearch.created[-1]
        thread.result_ready.emit(snapshot)
        thread.finished.emit()
        return self.leases.pending

    def test_typed_and_local_voice_use_actual_history_not_search(self):
        for submit in (self.send, self.voice):
            submit("Akiha, please Play music on Spotify")
            self.assertEqual(composition._ControlledAction.created, [])
            pending = self.deliver()
            self.assertEqual(len(pending.choices), 2)
            self.assertIn("recently played", self.panel._label.text())
            self.assertIn("HISTORY_PRIVATE_SENTINEL", self.panel._choices.itemText(0))
            self.assertEqual(self.provider.prompts, [])
            self.assertEqual(self.chat.messages, ())
            self.panel._resolve(cancel=True)
        self.assertTrue(all("recently-played?limit=20" in url for url in self.calls))

    def test_specific_track_artist_album_playlist_keep_existing_routes(self):
        for text, action in (
            (
                "Play track Blinding Lights by The Weeknd on Spotify",
                "spotify.play_track",
            ),
            ("Play artist Ado on Spotify", "spotify.play_artist"),
            ("Play album The Dark Side of the Moon on Spotify", "spotify.play_album"),
            ("Play playlist Chill on Spotify", "spotify.play_playlist"),
        ):
            self.window.set_busy(False)
            self.send(text)
            self.assertEqual(
                composition._ControlledAction.created[-1]._request.action_id, action
            )
            self.assertIsNone(self.leases.pending)
        self.assertEqual(composition._ControlledSearch.created, [])
        self.assertEqual(self.calls, [])

    def test_switch_to_song_artist_search_keeps_original_ownership(self):
        self.send("Play music on Spotify")
        pending = self.deliver()
        self.panel._spotify_mode.setCurrentIndex(1)
        self.panel._answer.setText("Blinding Lights")
        self.panel._artist.setText("The Weeknd")
        self.panel._submit.click()
        request = composition._ControlledAction.created[-1]._request
        self.assertEqual(request.correlation_id, pending.request.correlation_id)
        self.assertEqual(
            request.parameters,
            {
                "service": "spotify",
                "track_query": "Blinding Lights",
                "artist_query": "The Weeknd",
            },
        )

    def test_stale_account_change_expiry_and_replay_fail_closed(self):
        self.send("Play music on Spotify")
        pending = self.deliver()
        answer = ClarificationAnswer(
            pending.identity,
            ClarificationAnswerSource.LOCAL_UI,
            choice_id=pending.choice_ids[0],
        )
        self.state["settings_window"].spotify_session_changed.emit()
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )
        self.assertEqual(composition._ControlledAction.created, [])

    def test_missing_scope_empty_history_and_api_failure_never_search_or_execute(self):
        for status in (
            HistoryStatus.MISSING_SCOPE,
            HistoryStatus.EMPTY,
            HistoryStatus.RATE_LIMITED,
            HistoryStatus.FAILED,
        ):
            self.send("Play music on Spotify")
            composition._ControlledSearch.created[-1].result_ready.emit(
                SpotifyHistorySnapshot(status)
            )
            composition._ControlledSearch.created[-1].finished.emit()
            self.assertEqual(self.panel._choices.count(), 0)
            self.assertTrue(self.panel._answer.isHidden())
            self.assertTrue(self.panel._submit.isHidden())
            self.panel._resolve(cancel=True)
        self.assertEqual(composition._ControlledAction.created, [])
        self.assertEqual(self.provider.prompts, [])
        self.assertEqual(self.chat.messages, ())

    def test_history_titles_and_ids_absent_from_all_connected_outputs(self):
        self.send("Play music on Spotify")
        pending = self.deliver()
        ids = pending.choice_ids
        self.panel._submit.click()
        worker = composition._ControlledAction.created[-1]
        executor = SimpleNamespace(
            action_id="spotify.play_track",
            executor_id="spotify_play_track",
            execute=AsyncMock(
                return_value=ActionExecutionResult(
                    ActionStatus.SUCCESS,
                    "Playing HISTORY_PRIVATE_SENTINEL",
                    metadata={
                        "track_name": "HISTORY_PRIVATE_SENTINEL",
                        "track_uri": "spotify:track:one",
                    },
                )
            ),
        )
        # Use real validation, permission, bridge and SQLite action-audit routing;
        # only the external playback executor is replaced to avoid real playback.
        service = self.state["assistant_action_service"]
        with patch.dict(service._executors, {"spotify_play_track": executor}):
            dispatch = asyncio.run(worker._dispatch())
        executor.execute.assert_awaited_once()
        self.assertIs(dispatch.result.status, ActionStatus.SUCCESS)
        audits = asyncio.run(
            self.state["action_repository"].get_recent_action_audits(limit=10)
        )
        self.assertTrue(audits)
        self.assertEqual(audits[0].normalized_target, "spotify")
        worker.result_ready.emit(dispatch)
        worker.finished.emit()
        self.window.set_busy(False)
        self.send("I prefer public coffee with oat milk.")
        memories = asyncio.run(self.state["memory_repository"].get_recent_memories(100))
        self.assertTrue(memories)
        exported = render_chat_transcript(
            asyncio.run(self.chat.get_export_messages()), assistant_name="Akiha"
        )
        provider_input = asyncio.run(
            self.chat.build_provider_messages("public followup")
        )
        asyncio.run(self.chat.start_new_conversation())
        self.state["voice_controller"].apply_config(
            replace(self.state["voice_controller"].config, enabled=True)
        )
        self.state["integration_notification_coordinator"]._preference_provider = (
            lambda: replace(
                self.state["config"].integrations, voice_notifications_enabled=False
            )
        )
        self.window.show()
        self.state["test_external_integration_notification"]("gmail")
        for _ in range(10):
            self.app.processEvents()
        self.assertTrue(self.state["notification_repository"].list_recent())
        with closing(sqlite3.connect(self.state["paths"].database_path)) as c:
            tables = {
                name: c.execute('SELECT * FROM "' + name + '"').fetchall()
                for (name,) in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertIn("coffee", repr(tables["conversations"]))
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        self.assertIn("proactive.suggestion_delivered", logs)
        surfaces = "\n".join(
            (
                self.window._history_view.toPlainText(),
                repr(self.chat.messages),
                repr(self.provider.prompts),
                repr(provider_input),
                repr(tables),
                exported,
                repr(memories),
                repr(self.events),
                logs,
            )
        )
        self.assertNotIn("HISTORY_PRIVATE_SENTINEL", surfaces)
        self.assertNotIn("HISTORY_ARTIST_SENTINEL", surfaces)
        for opaque in ids:
            self.assertNotIn(opaque, surfaces)
