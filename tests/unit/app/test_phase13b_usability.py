"""Incomplete local actions through the composed typed and voice UI routes."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import unittest
from contextlib import closing
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import AsyncMock, patch

from project_akiha.core.actions import (
    FILE_OPEN_CAPABILITY,
    ActionExecutionResult,
    ActionRequest,
    ActionStatus,
    PermissionDecision,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.core.events import EventType
from project_akiha.services.transcript_export import render_chat_transcript
from tests.unit.app import test_phase13b_composition as composition
from tests.unit.services.test_action_clarification import FakeClock


class Phase13BUsabilityTest(unittest.TestCase):
    # Reuse graph setup/teardown only, without inheriting or duplicating its tests.
    release_graph = composition.Phase13BCompositionTest.release_graph
    send = composition.Phase13BCompositionTest.send
    wait_chat = composition.Phase13BCompositionTest.wait_chat

    @classmethod
    def setUpClass(cls):
        composition.Phase13BCompositionTest.setUpClass()
        cls.app = composition.Phase13BCompositionTest.app

    def setUp(self):
        composition.Phase13BCompositionTest.setUp(self)
        self.panel = self.state["clarification_panel"]
        self.permissions = self.state["assistant_permission_service"]
        self.catalog = self.state["application_catalog"]
        self.catalog._environment = MappingProxyType(
            {"LOCALAPPDATA": str(self.root / "Catalog")}
        )

    def install_app(self, *, grant=True):
        exe = self.root / "Catalog" / "Spotify" / "Spotify.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"synthetic availability fixture; never executed")
        if grant:
            asyncio.run(self.permissions.grant_application("spotify"))
        return exe

    def voice(self, text):
        presenter = self.state["chat_voice_presenter"]
        presenter.apply_config(
            replace(presenter._config, auto_send_transcript_enabled=True)
        )
        self.state["event_bus"].publish(
            EventType.VOICE_TRANSCRIPT_READY,
            {"text": text, "requires_review": False},
        )
        self.wait_chat()

    def selected_answer(self, pending=None, **kwargs):
        pending = pending or self.leases.pending
        return ClarificationAnswer(
            pending.identity,
            ClarificationAnswerSource.LOCAL_UI,
            choice_id=pending.choice_ids[0],
            **kwargs,
        )

    def select(self):
        before = len(composition._ControlledAction.created)
        self.panel._choices.setCurrentIndex(0)
        self.panel._submit.click()
        self.assertEqual(len(composition._ControlledAction.created), before + 1)
        return composition._ControlledAction.created[-1]

    def assert_picker(self, action, label):
        pending = self.leases.pending
        self.assertIsNotNone(pending)
        self.assertEqual(pending.request.action_id, action)
        self.assertEqual(pending.local_targets.labels, (label,))
        self.assertFalse(self.panel._choices.isHidden())
        self.assertTrue(self.panel._answer.isHidden())
        self.assertTrue(self.panel._any.isHidden())
        self.assertEqual(self.panel._choices.itemText(0), label)
        self.assertEqual(self.panel._choices.itemData(0), pending.choice_ids[0])
        self.assertRegex(pending.choice_ids[0], r"^[a-f0-9]{32}$")
        return pending

    def test_typed_bare_and_bounded_name_courtesy_commands_have_choices(self):
        self.install_app()
        for prefix in ("", "please ", "Akiha, ", "Akiha, please ", "please Akiha, "):
            for command, action, label in (
                ("Open an app.", "applications.launch", "Spotify"),
                ("Open a folder.", "files.open_directory", "Approved"),
            ):
                with self.subTest(prefix=prefix, command=command):
                    self.send(prefix + command)
                    self.assert_picker(action, label)
        self.assertEqual(self.chat.messages, ())
        self.assertEqual(self.provider.prompts, [])

    def test_local_voice_uses_the_same_bare_and_prefixed_picker(self):
        self.install_app()
        for prefix in ("", "please ", "Akiha, ", "Akiha, please ", "please Akiha, "):
            for command, action, label in (
                ("Open an app.", "applications.launch", "Spotify"),
                ("Open a folder.", "files.open_directory", "Approved"),
            ):
                with self.subTest(prefix=prefix, command=command):
                    self.voice(prefix + command)
                    self.assert_picker(action, label)
        self.assertEqual(self.chat.messages, ())
        self.assertEqual(self.provider.prompts, [])

    def test_manual_voice_downloads_alias_rejected_and_opaque_root_opens_twice(self):
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        downloads = self.root / "Downloads"
        downloads.mkdir()
        asyncio.run(self.permissions.grant_directory(FILE_OPEN_CAPABILITY, downloads))
        service = self.state["assistant_action_service"]
        executor = service._executors["open_directory"]
        safe_execute = AsyncMock(
            return_value=ActionExecutionResult(ActionStatus.SUCCESS, "Opened locally.")
        )
        with patch.object(executor, "execute", safe_execute):
            for _ in range(2):
                self.voice("Open a folder.")
                pending = self.assert_picker("files.open_directory", "Downloads")
                raw = ClarificationAnswer(
                    pending.identity, ClarificationAnswerSource.LOCAL_UI, "Downloads"
                )
                self.assertIs(
                    self.controller.resolve(raw).outcome, ClarificationOutcome.INVALID
                )
                self.assertEqual(self.leases.pending.identity, pending.identity)
                # Hidden free text cannot influence the actual picker submission.
                self.panel._answer.setText("Downloads")
                worker = self.select()
                request = worker._request
                self.assertEqual(request.parameters["path"], str(downloads.resolve()))
                self.assertEqual(request.correlation_id, pending.request.correlation_id)
                self.assertTrue(worker._ownership_guard())
                result = asyncio.run(service.evaluate_request(request))
                self.assertIs(result.status, ActionStatus.SUCCESS)
                self.assertIs(result.permission_decision, PermissionDecision.GRANTED)
                self.assertNotIn(
                    "invalid assistant action", self.window._history_view.toPlainText()
                )
        self.assertEqual(safe_execute.await_count, 2)
        raw_request = ActionRequest(
            "raw-alias", "files.open_directory", "chat", {"path": "Downloads"}
        )
        self.assertIs(
            asyncio.run(service.evaluate_request(raw_request)).status,
            ActionStatus.DENIED,
        )

    def test_application_choice_keeps_request_operation_and_dispatch_policy(self):
        self.install_app()
        self.send("Open an app.")
        pending = self.assert_picker("applications.launch", "Spotify")
        worker = self.select()
        self.assertEqual(worker._request.parameters, {"application_id": "spotify"})
        self.assertEqual(worker._request.correlation_id, pending.request.correlation_id)
        self.assertEqual(worker._request.source, "chat")
        executor = self.state["assistant_action_service"]._executors[
            "launch_allowlisted_application"
        ]
        with patch.object(
            executor,
            "execute",
            AsyncMock(
                return_value=ActionExecutionResult(
                    ActionStatus.SUCCESS, "Opened locally."
                )
            ),
        ) as execute:
            result = asyncio.run(worker._dispatch()).result
        execute.assert_awaited_once()
        self.assertIs(result.permission_decision, PermissionDecision.GRANTED)

    def test_no_roots_shows_configuration_guidance_without_answer_field(self):
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        for submit in (self.send, self.voice):
            submit("Open a folder.")
            self.assertEqual(self.leases.pending.choices, ())
            self.assertIn("Configure an approved folder", self.panel._label.text())
            self.assertTrue(self.panel._answer.isHidden())
            self.assertTrue(self.panel._submit.isHidden())
            self.assertTrue(self.panel._choices.isHidden())

    def test_unavailable_and_ungranted_apps_are_not_offered(self):
        self.install_app(grant=False)
        asyncio.run(self.permissions.grant_application("discord"))
        for submit in (self.send, self.voice):
            submit("Open an app.")
            self.assertEqual(self.leases.pending.choices, ())
            self.assertIn("launch permission in Settings", self.panel._label.text())
            self.assertTrue(self.panel._answer.isHidden())
            self.assertTrue(self.panel._submit.isHidden())
        asyncio.run(self.permissions.grant_application("spotify"))
        self.send("Open an app.")
        self.assert_picker("applications.launch", "Spotify")

    def test_removed_and_revoked_roots_fail_closed(self):
        self.send("Open a folder.")
        answer = self.selected_answer()
        self.approved.rmdir()
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.INVALID
        )
        self.assertIsNone(self.leases.pending)
        self.approved.mkdir()
        self.voice("Open a folder.")
        answer = self.selected_answer()
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )
        self.assertEqual(composition._ControlledAction.created, [])

        asyncio.run(
            self.permissions.grant_directory(FILE_OPEN_CAPABILITY, self.approved)
        )
        self.send("Open a folder.")
        queued = self.select()
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        self.assertFalse(queued._ownership_guard())
        self.assertIs(
            asyncio.run(queued._dispatch()).result.permission_decision,
            PermissionDecision.MISSING,
        )

    def test_removed_and_revoked_apps_fail_closed(self):
        exe = self.install_app()
        self.send("Open an app.")
        answer = self.selected_answer()
        exe.unlink()
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.INVALID
        )
        self.install_app()
        self.voice("Open an app.")
        answer = self.selected_answer()
        asyncio.run(self.permissions.revoke_application("spotify"))
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )
        self.assertEqual(composition._ControlledAction.created, [])

        self.install_app()
        self.send("Open an app.")
        queued = self.select()
        asyncio.run(self.permissions.revoke_application("spotify"))
        self.assertFalse(queued._ownership_guard())
        self.assertIs(
            asyncio.run(queued._dispatch()).result.permission_decision,
            PermissionDecision.MISSING,
        )

    def test_exact_expiry_and_single_use_selection(self):
        self.leases.clock = FakeClock()
        for seconds, expected in (
            (119.999, ClarificationOutcome.RESOLVED),
            (120.0, ClarificationOutcome.EXPIRED),
        ):
            self.send("Open a folder.")
            pending = self.leases.pending
            answer = self.selected_answer(pending)
            self.leases.clock.seconds = pending.identity.created_at + seconds
            self.assertIs(self.controller.resolve(answer).outcome, expected)
            self.assertIs(
                self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
            )

    def test_cancel_and_supersession_reject_old_opaque_selection(self):
        self.install_app()
        for supersede in (False, True):
            self.send("Open a folder.")
            answer = self.selected_answer()
            if supersede:
                self.voice("Open an app.")
                newest = self.leases.pending.identity
            else:
                self.panel._resolve(cancel=True)
                newest = None
            self.assertIs(
                self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
            )
            self.assertEqual(
                self.leases.pending.identity if self.leases.pending else None, newest
            )
        self.assertEqual(composition._ControlledAction.created, [])

    def test_opaque_choices_are_local_ui_only_and_bound_to_the_lease(self):
        self.send("Open a folder.")
        answer = self.selected_answer()
        for source in (
            ClarificationAnswerSource.PROVIDER,
            ClarificationAnswerSource.LOCAL_TEXT,
            ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT,
        ):
            self.assertIs(
                self.controller.resolve(replace(answer, source=source)).outcome,
                ClarificationOutcome.INVALID,
            )
        for forged in (
            replace(answer, choice_id="unknown"),
            replace(answer, choice_index=1),
            replace(answer, value="Approved"),
            replace(answer, open_any=True),
        ):
            self.assertIs(
                self.controller.resolve(forged).outcome, ClarificationOutcome.INVALID
            )
        self.voice("Open a folder.")
        new_answer = self.selected_answer()
        self.assertNotEqual(answer.choice_id, new_answer.choice_id)
        self.assertIs(
            self.controller.resolve(
                replace(new_answer, choice_id=answer.choice_id)
            ).outcome,
            ClarificationOutcome.INVALID,
        )

    def test_new_action_during_resolution_notification_wins_without_old_enqueue(self):
        self.install_app()
        self.send("Open a folder.")
        original = self.controller.on_pending

        def publish_newer():
            self.controller.on_pending = original
            self.voice("Open an app.")

        self.controller.on_pending = publish_newer
        self.addCleanup(setattr, self.controller, "on_pending", original)
        self.panel._submit.click()
        self.assert_picker("applications.launch", "Spotify")
        self.assertEqual(composition._ControlledAction.created, [])

    def test_fingerprint_and_confirmation_guarantees_survive_choice_resolution(self):
        self.leases.clock = FakeClock()
        self.send("Open a folder.")
        resolved = self.controller.resolve(self.selected_answer()).request
        epoch = self.leases.owner_epoch
        confirmation = self.leases.issue_confirmation(resolved, owner_epoch=epoch)
        changed = replace(resolved, parameters={"path": str(self.approved / "changed")})
        self.assertFalse(self.controller.prepare(changed))
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, resolved, approved=True)
        )
        self.send("Open a folder.")
        resolved = self.controller.resolve(self.selected_answer()).request
        confirmation = self.leases.issue_confirmation(resolved)
        self.leases.clock.seconds = confirmation.deadline
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, resolved, approved=True)
        )
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, resolved, approved=True)
        )

    def test_unbound_provider_clarify_keeps_the_generic_cancel_only_notice(self):
        self.state["assistant_tool_gateway"].set_enabled(True)
        self.provider.generate_response = AsyncMock(
            return_value='{"action":"clarify","topic":"directory"}'
        )
        self.send("Please open something.")
        deadline = time.monotonic() + 5
        while self.state["active_tool_threads"] and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.001)
        self.assertEqual(self.state["active_tool_threads"], [])
        self.assertIsNone(self.leases.pending)
        self.assertEqual(
            self.panel._label.text(),
            "Please issue one explicit action with its exact target.",
        )
        for widget in (self.panel._choices, self.panel._answer, self.panel._submit):
            self.assertTrue(widget.isHidden())
        self.assertEqual(composition._ControlledAction.created, [])

    def test_arbitrary_prose_negation_and_repeated_prefixes_do_not_create_actions(self):
        for text in (
            "I wondered whether you can open an app.",
            "Akiha, do not open a folder.",
            "Akiha, Akiha, open a folder.",
            "x" * 2001 + " open a folder.",
        ):
            self.assertIsNone(self.controller.incomplete_command(text, "bounded-probe"))
        self.send("I prefer public coffee with oat milk.")
        self.assertIsNone(self.leases.pending)
        self.assertTrue(self.chat.messages)
        self.assertTrue(self.provider.prompts)

    def test_picker_paths_answers_and_ids_stay_out_of_connected_persistence(self):
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        secret_root = self.root / "PICKER_SECRET"
        secret_root.mkdir()
        asyncio.run(self.permissions.grant_directory(FILE_OPEN_CAPABILITY, secret_root))
        ids = []
        for submit in (self.send, self.voice):
            submit("Akiha, please open a folder.")
            pending = self.assert_picker("files.open_directory", "PICKER_SECRET")
            ids.extend(pending.choice_ids)
            self.send("I prefer PICKER_SECRET/ Private Answer.mp3")
            self.assertEqual(self.leases.pending.identity, pending.identity)
            self.assertEqual(self.chat.messages, ())
            self.assertEqual(self.provider.prompts, [])
            self.assertNotIn("PICKER_SECRET", self.panel._label.text())
            self.select()
            self.window.set_busy(False)
        self.send("I prefer public coffee with oat milk.")
        memories = asyncio.run(self.state["memory_repository"].get_recent_memories(100))
        self.assertTrue(memories)
        exported = render_chat_transcript(
            asyncio.run(self.chat.get_export_messages()), assistant_name="Akiha"
        )
        messages = asyncio.run(self.chat.build_provider_messages("public followup"))
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
        with closing(sqlite3.connect(self.state["paths"].database_path)) as connection:
            tables = {
                name: connection.execute('SELECT * FROM "' + name + '"').fetchall()
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        # Configured roots necessarily exist in the permission repository;
        # clarification must not copy them to any conversation/output table.
        root_tables = [
            name for name, rows in tables.items() if "PICKER_SECRET" in repr(rows)
        ]
        self.assertEqual(root_tables, ["assistant_action_permissions"])
        del tables["assistant_action_permissions"]
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
                repr(messages),
                repr(tables),
                exported,
                repr(memories),
                repr(self.events),
                logs,
            )
        )
        self.assertNotIn("PICKER_SECRET", surfaces)
        for choice_id in ids:
            self.assertNotIn(choice_id, surfaces)

    def test_vague_spotify_music_typed_and_voice_stays_local_until_target_selection(
        self,
    ):
        for submit in (self.send, self.voice):
            for prefix in ("", "Akiha, please "):
                submit(prefix + "Play Music on Spotify")
                self.assertEqual(
                    self.leases.pending.request.action_id, "spotify.play_track"
                )
                self.assertEqual(
                    self.leases.pending.request.parameters, {"service": "spotify"}
                )
                self.assertIn("Spotify recently played", self.panel._label.text())
                self.assertEqual(composition._ControlledAction.created, [])
                self.assertEqual(self.chat.messages, ())
                self.assertEqual(self.provider.prompts, [])
        self.panel._spotify_mode.setCurrentIndex(1)
        pending = self.leases.pending
        self.panel._answer.setText("SPOTIFY_TARGET_SENTINEL")
        self.panel._submit.click()
        worker = composition._ControlledAction.created[-1]
        self.assertEqual(worker._request.correlation_id, pending.request.correlation_id)
        self.assertEqual(worker._request.action_id, "spotify.play_track")
        self.assertEqual(
            worker._request.parameters["track_query"], "SPOTIFY_TARGET_SENTINEL"
        )
        self.assertNotIn("SPOTIFY_TARGET_SENTINEL", repr(self.chat.messages))
        self.assertNotIn("SPOTIFY_TARGET_SENTINEL", repr(self.provider.prompts))
        exported = render_chat_transcript(
            asyncio.run(self.chat.get_export_messages()), assistant_name="Akiha"
        )
        self.assertNotIn("SPOTIFY_TARGET_SENTINEL", exported)
        with closing(sqlite3.connect(self.state["paths"].database_path)) as connection:
            rows = connection.execute("SELECT * FROM messages").fetchall()
        self.assertNotIn("SPOTIFY_TARGET_SENTINEL", repr(rows))

    def test_specific_spotify_track_keeps_deterministic_title_and_artist_route(self):
        self.send("Play track Blinding Lights by The Weeknd on Spotify")
        self.assertIsNone(self.leases.pending)
        self.assertEqual(len(composition._ControlledAction.created), 1)
        request = composition._ControlledAction.created[-1]._request
        self.assertEqual(request.action_id, "spotify.play_track")
        self.assertEqual(
            request.parameters,
            {
                "service": "spotify",
                "track_query": "Blinding Lights",
                "artist_query": "The Weeknd",
            },
        )
        self.assertEqual(self.chat.messages, ())
        self.assertEqual(self.provider.prompts, [])


if __name__ == "__main__":
    unittest.main()
