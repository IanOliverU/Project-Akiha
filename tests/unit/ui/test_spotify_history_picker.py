"""Production picker/fetch callbacks with real Qt workers and SQLite permissions.

This bounded production callback composition does not replace the full-app gate.
"""

from __future__ import annotations

import ast
import asyncio
import os
import sqlite3
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication

from project_akiha.app import main
from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.config import SpotifyConfig
from project_akiha.core.actions import ActionRequest, ProtectedPathPolicy
from project_akiha.database import SQLiteActionRepository
from project_akiha.integrations.spotify.auth import SpotifyToken
from project_akiha.integrations.spotify.client import SpotifyClient
from project_akiha.integrations.spotify.history import (
    HISTORY_SCOPE,
    fetch_spotify_history,
    history_choices,
)
from project_akiha.integrations.spotify.session import SpotifySession
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.assistant_permissions import AssistantPermissionService
from project_akiha.ui.action_clarification_panel import ActionClarificationPanel
from project_akiha.ui.spotify_history_worker import SpotifyHistoryThread
from tests.unit.integrations.spotify.test_history import play
from tests.unit.integrations.spotify.test_session import _SecretStore


class SpotifyHistoryPickerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.leases = ActionClarificationService()
        self.controller = ActionClarificationController(self.leases)
        self.permissions = AssistantPermissionService(
            SQLiteActionRepository(self.root / "history.sqlite3"),
            ProtectedPathPolicy(protected_roots=(self.root / "Protected",)),
            on_change=self.controller.invalidate,
        )
        asyncio.run(self.permissions.grant_spotify_playback())
        self.config = SpotifyConfig(enabled=True, client_id="a" * 32)
        self.session = SpotifySession(
            self.config,
            _SecretStore("refresh"),
            token_refresher=lambda *_: SpotifyToken(
                "access", "refresh", 200, (HISTORY_SCOPE,)
            ),
            now=lambda: 100,
        )
        self.payload = {
            "items": [play("one"), play("one"), play("two", playable=False)]
        }
        self.requests = []

        def transport(url, headers, timeout):
            self.requests.append(url)
            return self.payload

        self.client = SpotifyClient(self.config, self.session, transport=transport)
        self.executed = Mock()
        self.panel = ActionClarificationPanel(
            self.controller, Mock(), on_owned_resolved=self.executed
        )
        self.controller.on_pending = self.panel.refresh
        self.threads = []
        self.all_threads = []

        def worker(*args):
            t = SpotifyHistoryThread(*args)
            self.all_threads.append(t)
            return t

        namespace = dict(vars(main))
        namespace.update(
            action_clarification=self.controller,
            clarification_panel=self.panel,
            spotify_session=self.session,
            spotify_client=self.client,
            assistant_permission_service=self.permissions,
            config=SimpleNamespace(spotify=self.config),
            active_tool_threads=self.threads,
            update_chat_busy_state=lambda: None,
            SpotifyHistoryThread=worker,
        )
        # Compile the actual application callbacks, without changing their bodies.
        tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
        run = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_run_application"
        )
        callbacks = [
            n
            for n in run.body
            if isinstance(n, ast.FunctionDef)
            and n.name in {"spotify_history_allowed", "start_spotify_history"}
        ]
        self.assertEqual(len(callbacks), 2)
        exec(
            compile(ast.Module(body=callbacks, type_ignores=[]), main.__file__, "exec"),
            namespace,
        )
        self.panel.spotify_history_requested.connect(namespace["start_spotify_history"])
        self.addCleanup(self.cleanup_qt)

    def cleanup_qt(self):
        for t in self.all_threads:
            try:
                t.cancel()
                self.assertTrue(t.wait(2000))
            except RuntimeError:
                pass  # Already deleted by the production finished callback.
        self.leases.invalidate()
        self.panel.close()
        self.panel.deleteLater()
        self.executed.reset_mock()
        self.all_threads.clear()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def begin(self):
        self.controller.prepare(
            self.controller.incomplete_command("Play music on Spotify", "picker")
        )

    def drain(self):
        end = time.monotonic() + 3
        while self.threads and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.001)
        self.app.processEvents()
        self.assertEqual(self.threads, [])

    def test_history_picker_uses_production_fetch_and_opaque_owned_selection(self):
        self.begin()
        self.drain()
        self.assertEqual(self.panel._choices.count(), 2)
        self.assertIn("distinct tracks", self.panel._label.text())
        self.assertTrue(self.panel._answer.isHidden())
        self.assertIn("HISTORY_ARTIST_SENTINEL", self.panel._choices.itemText(0))
        self.assertFalse(self.panel._choices.model().item(1).isEnabled())
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn("spotify:track", self.panel._choices.currentData())
        self.executed.assert_not_called()
        owner = self.leases.pending.identity.owner_epoch
        self.panel._submit.click()
        self.assertEqual(self.executed.call_count, 1)
        self.assertEqual(self.executed.call_args.args[1], owner)
        self.assertEqual(
            self.executed.call_args.args[0].parameters["track_uri"], "spotify:track:one"
        )
        self.assertEqual(self.panel._choices.count(), 0)
        self.assertIsNone(self.leases.pending)

    def test_search_mode_collects_title_and_artist_and_discards_history(self):
        self.begin()
        self.drain()
        self.panel._spotify_mode.setCurrentIndex(1)
        self.assertFalse(self.panel._answer.isHidden())
        self.assertFalse(self.panel._artist.isHidden())
        self.panel._answer.setText("Blinding Lights")
        self.panel._artist.setText("The Weeknd")
        self.panel._submit.click()
        self.assertEqual(
            self.executed.call_args.args[0].parameters,
            {
                "service": "spotify",
                "track_query": "Blinding Lights",
                "artist_query": "The Weeknd",
            },
        )

    def test_missing_scope_explains_reconnect_and_does_not_search(self):
        self.session._token_refresher = lambda *_: SpotifyToken(
            "access", "refresh", 200, ()
        )
        self.begin()
        self.drain()
        self.assertIn("Reconnect", self.panel._label.text())
        self.assertEqual(self.panel._choices.count(), 0)
        self.assertEqual(self.requests, [])
        self.executed.assert_not_called()

    def test_empty_history_has_no_arbitrary_selection_or_search(self):
        self.payload = {"items": []}
        self.begin()
        self.drain()
        self.assertIn("No recent Spotify plays", self.panel._label.text())
        self.assertTrue(self.panel._submit.isHidden())
        self.executed.assert_not_called()

    def test_permission_revocation_while_worker_blocked_drops_late_history(self):
        entered, release = Event(), Event()

        def blocked(*_):
            entered.set()
            self.assertTrue(release.wait(2))
            return self.payload

        self.client._transport = blocked
        self.begin()
        self.assertTrue(entered.wait(2))
        asyncio.run(self.permissions.revoke_spotify_playback())
        release.set()
        self.drain()
        self.assertIsNone(self.leases.pending)
        self.assertEqual(self.panel._choices.count(), 0)
        self.executed.assert_not_called()

    def test_supersession_while_worker_blocked_preserves_newer_clarification(self):
        entered, release = Event(), Event()

        def blocked(*_):
            entered.set()
            self.assertTrue(release.wait(2))
            return self.payload

        self.client._transport = blocked
        self.begin()
        self.assertTrue(entered.wait(2))
        self.controller.prepare(
            ActionRequest("newer", "applications.launch", "chat", {})
        )
        identity = self.leases.pending.identity
        release.set()
        self.drain()
        self.assertEqual(self.leases.pending.identity, identity)
        self.assertTrue(self.panel._spotify_mode.isHidden())
        self.assertEqual(self.panel._choices.count(), 0)

    def test_local_search_mode_drops_queued_history_result(self):
        entered, release = Event(), Event()

        def blocked(*_):
            entered.set()
            self.assertTrue(release.wait(2))
            return self.payload

        self.client._transport = blocked
        self.begin()
        self.assertTrue(entered.wait(2))
        self.panel._spotify_mode.setCurrentIndex(1)
        identity = self.leases.pending.identity
        release.set()
        self.drain()
        self.assertEqual(self.leases.pending.identity, identity)
        self.assertEqual(self.panel._choices.count(), 0)
        self.assertFalse(self.panel._artist.isHidden())

    def test_history_list_and_choice_ids_never_enter_permission_database(self):
        self.begin()
        self.drain()
        ids = self.leases.pending.choice_ids
        with sqlite3.connect(self.root / "history.sqlite3") as c:
            rows = "\n".join(
                repr(c.execute('SELECT * FROM "' + name + '"').fetchall())
                for (name,) in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )
        self.assertNotIn("SENTINEL", rows)
        for opaque in ids:
            self.assertNotIn(opaque, rows)


class SpotifyStandalonePickerTest(unittest.TestCase):
    """Real widgets/worker without requiring a Windows asyncio IPC socket pair."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.leases = ActionClarificationService()
        self.controller = ActionClarificationController(self.leases)
        self.executed = Mock()
        self.panel = ActionClarificationPanel(
            self.controller, Mock(), on_owned_resolved=self.executed
        )
        self.controller.on_pending = self.panel.refresh
        config = SpotifyConfig(enabled=True, client_id="a" * 32)
        self.session = SpotifySession(
            config,
            _SecretStore("refresh"),
            token_refresher=lambda *_: SpotifyToken(
                "access", "refresh", 200, (HISTORY_SCOPE,)
            ),
            now=lambda: 100,
        )
        self.client = SpotifyClient(
            config,
            self.session,
            transport=lambda *_: {"items": [play("one"), play("one"), play("two")]},
        )
        self.workers = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for worker in self.workers:
            worker.cancel()
            self.assertTrue(worker.wait(2000))
            worker.deleteLater()
        self.leases.invalidate()
        self.executed.reset_mock()
        destroyed = []
        self.panel.destroyed.connect(
            lambda: destroyed.append(QThread.currentThread() == self.app.thread())
        )
        self.panel.close()
        self.panel.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertEqual(destroyed, [True])
        self.workers.clear()

    def begin(self):
        request = self.controller.incomplete_command(
            "Play music on Spotify", "standalone"
        )
        self.controller.prepare(request)
        identity = self.leases.pending.identity
        return self.leases.start_spotify_history(identity, self.session.generation)

    def test_new_default_and_owned_history_selection_use_real_widgets(self):
        requested = []
        self.panel.spotify_history_requested.connect(requested.append)
        captured = self.begin()
        self.assertEqual(requested, [captured.lease])
        snapshot = fetch_spotify_history(
            self.client, self.session, self.session.generation
        )
        self.assertTrue(
            self.leases.publish_spotify_history(
                captured,
                history_choices(captured.request, snapshot),
                account_guard=lambda: True,
            )
        )
        self.panel.refresh()
        self.assertEqual(self.panel._choices.count(), 2)
        self.assertTrue(self.panel._answer.isHidden())
        self.executed.assert_not_called()
        self.panel._submit.click()
        self.assertEqual(self.executed.call_count, 1)
        self.assertEqual(
            self.executed.call_args.args[0].parameters["track_uri"], "spotify:track:one"
        )
        self.assertEqual(self.panel._choices.count(), 0)

    def test_optional_artist_is_submitted_only_from_local_search_fields(self):
        self.begin()
        self.panel._spotify_mode.setCurrentIndex(1)
        self.panel._answer.setText("song")
        self.panel._artist.setText("artist")
        self.panel._submit.click()
        self.assertEqual(
            self.executed.call_args.args[0].parameters,
            {"service": "spotify", "track_query": "song", "artist_query": "artist"},
        )
        self.assertEqual(self.panel._artist.text(), "")

    def test_real_worker_fetches_history_and_is_joined(self):
        captured = self.begin()
        worker = SpotifyHistoryThread(self.client, self.session, captured)
        self.workers.append(worker)
        results = []
        worker.result_ready.connect(results.append)
        worker.start()
        self.assertTrue(worker.wait(2000))
        self.app.processEvents()
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0].tracks), 2)

    def test_cancellation_during_real_worker_drops_result(self):
        entered, release = Event(), Event()

        def transport(*_):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("barrier timeout")
            return {"items": [play("one")]}

        self.client._transport = transport
        captured = self.begin()
        worker = SpotifyHistoryThread(self.client, self.session, captured)
        self.workers.append(worker)
        results = []
        worker.result_ready.connect(results.append)
        worker.start()
        self.assertTrue(entered.wait(2))
        worker.cancel()
        self.leases.invalidate()
        release.set()
        self.assertTrue(worker.wait(2000))
        self.app.processEvents()
        self.assertEqual(results, [])
        self.assertIsNone(self.leases.pending)
