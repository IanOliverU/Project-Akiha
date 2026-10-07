"""Music registration, choices and privacy through the actual app composition."""

from __future__ import annotations

import asyncio
import sqlite3
import unittest
from contextlib import closing
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from project_akiha.config import load_config
from project_akiha.core.actions import (
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
    ActionExecutionResult,
    ActionStatus,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.services.transcript_export import render_chat_transcript
from tests.unit.app import test_phase13b_composition as composition
from tests.unit.app import test_phase13b_usability as usability
from tests.unit.services.test_action_clarification import FakeClock


class MusicFilesCompositionTest(unittest.TestCase):
    # Share only setup/teardown and routing helpers; do not inherit existing tests.
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
        self.settings = self.state["settings_window"]
        self.music = self.settings._music_files_panel
        self.panel = self.state["clarification_panel"]
        self.permissions = self.state["assistant_permission_service"]
        self.state["refresh_assistant_permissions"]()

    def song(self, name="Song.mp3", *, approved=True):
        path = (self.approved if approved else self.root) / name
        path.write_bytes(b"synthetic music fixture; never played")
        return path.resolve()

    def register(self, *paths):
        self.music.register(tuple(map(str, paths)))

    def answer(self, index=0):
        pending = self.leases.pending
        return ClarificationAnswer(
            pending.identity,
            ClarificationAnswerSource.LOCAL_UI,
            choice_id=pending.choice_ids[index],
        )

    def drop(self, mime):
        viewport = self.music._list.viewport()
        enter = QDragEnterEvent(
            QPoint(10, 10),
            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(viewport, enter)
        drop = QDropEvent(
            QPointF(10, 10),
            Qt.DropAction.CopyAction | Qt.DropAction.MoveAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        self.app.sendEvent(viewport, drop)
        return enter.isAccepted(), drop.isAccepted(), drop.dropAction()

    def test_real_file_drop_persists_references_immediately_and_deduplicates(self):
        song = self.song("Drop with spaces.mp3")
        original = song.read_bytes()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(song))])
        self.assertEqual(self.drop(mime), (True, True, Qt.DropAction.CopyAction))
        self.assertEqual(self.music._list.count(), 1)
        saved = load_config(config_path=self.state["user_config_store"].config_path)
        self.assertEqual(saved.music_files.paths, (str(song),))
        self.drop(mime)
        self.assertEqual(self.music._list.count(), 1)
        self.assertEqual(song.read_bytes(), original)

    def test_file_picker_filter_and_remove_never_delete_source(self):
        first, second = self.song("First.mp3"), self.song("Second.flac")
        with patch(
            "project_akiha.ui.music_files_panel.QFileDialog.getOpenFileNames",
            return_value=([str(first), str(second)], "Music files"),
        ):
            self.music._add.click()
        self.music._search.setText("FIRST")
        self.assertEqual(self.music._list.count(), 1)
        self.music._list.item(0).setSelected(True)
        self.music._remove.click()
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.music._search.clear()
        self.assertEqual(self.music._config.paths, (str(second),))
        self.assertEqual(
            load_config(
                config_path=self.state["user_config_store"].config_path
            ).music_files.paths,
            (str(second),),
        )

    def test_typed_and_local_voice_offer_every_registered_file_over_search_limit(self):
        songs = tuple(self.song(f"Song {i:02}.mp3") for i in range(25))
        self.register(*songs)
        for submit in (self.send, self.voice):
            for prefix in (
                "",
                "please ",
                "Akiha, ",
                "Akiha, please ",
                "please Akiha, ",
            ):
                submit(prefix + "Open a music file.")
                pending = self.leases.pending
                self.assertEqual(pending.request.action_id, "files.open")
                self.assertEqual(pending.request.source, "chat.music")
                self.assertTrue(pending.spec.local_music_catalog)
                self.assertEqual(len(pending.choices), 25)
                self.assertFalse(pending.local_targets.truncated)
                self.assertEqual(self.panel._choices.count(), 25)
                self.assertTrue(self.panel._answer.isHidden())
                for i, path in enumerate(songs):
                    self.assertEqual(pending.choices[i].parameters["path"], str(path))
                    self.assertRegex(self.panel._choices.itemData(i), r"^[a-f0-9]{32}$")
        self.assertEqual(self.chat.messages, ())
        self.assertEqual(self.provider.prompts, [])

    def test_opaque_choice_keeps_owner_and_requires_confirmation_before_execution(self):
        song = self.song()
        self.register(song)
        self.send("Open a music file.")
        pending, answer = self.leases.pending, self.answer()
        epoch = self.leases.owner_epoch
        self.panel._submit.click()
        worker = composition._ControlledAction.created[-1]
        self.assertEqual(worker._request.parameters, {"path": str(song)})
        self.assertEqual(worker._request.correlation_id, pending.request.correlation_id)
        self.assertEqual(self.leases.owner_epoch, epoch)
        self.assertTrue(worker._ownership_guard())
        service = self.state["assistant_action_service"]
        executor = service._executors["open_safe_file"]
        with patch.object(
            executor,
            "execute",
            AsyncMock(
                return_value=ActionExecutionResult(
                    ActionStatus.SUCCESS, "Opened locally."
                )
            ),
        ) as execute:
            self.assertIs(
                asyncio.run(worker._dispatch()).result.status,
                ActionStatus.CONFIRMATION_REQUIRED,
            )
            execute.assert_not_awaited()
            token = self.leases.issue_confirmation(worker._request, owner_epoch=epoch)
            self.assertTrue(
                self.leases.consume_confirmation(token, worker._request, approved=True)
            )
            self.assertFalse(
                self.leases.consume_confirmation(token, worker._request, approved=True)
            )
            self.assertIs(
                asyncio.run(
                    service.evaluate_request(worker._request, confirmed=True)
                ).status,
                ActionStatus.SUCCESS,
            )
            execute.assert_awaited_once()
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )

    def test_empty_catalog_has_settings_guidance_without_raw_path_field(self):
        for submit in (self.send, self.voice):
            submit("Open a music file.")
            self.assertEqual(self.leases.pending.choices, ())
            self.assertIn("Music files settings", self.panel._label.text())
            self.assertTrue(self.panel._answer.isHidden())
            self.assertTrue(self.panel._submit.isHidden())

    def test_unapproved_and_missing_entries_remain_visible_but_cannot_be_selected(self):
        outside, removed = self.song("Unapproved.mp3", approved=False), self.song(
            "Removed.mp3"
        )
        self.register(outside, removed)
        asyncio.run(self.permissions.remove_approved_directory(outside.parent))
        asyncio.run(self.permissions.remove_approved_directory(removed.parent))
        removed.unlink()
        self.send("Open a music file.")
        pending = self.leases.pending
        self.assertEqual(self.panel._choices.count(), 2)
        self.assertEqual(pending.local_targets.enabled, (False, False))
        self.assertIn("Needs folder approval", self.panel._choices.itemText(0))
        self.assertIn("Missing or unavailable", self.panel._choices.itemText(1))
        self.assertFalse(self.panel._submit.isEnabled())
        for i in range(2):
            self.assertIs(
                self.controller.resolve(self.answer(i)).outcome,
                ClarificationOutcome.INVALID,
            )
        self.assertEqual(composition._ControlledAction.created, [])
        asyncio.run(
            self.permissions.grant_directory(FILE_OPEN_CAPABILITY, outside.parent)
        )
        self.send("Open a music file.")
        self.assertTrue(self.leases.pending.local_targets.enabled[0])

    def test_removal_revocation_and_file_disappearance_invalidate_selection(self):
        song = self.song()
        self.register(song)
        self.send("Open a music file.")
        answer = self.answer()
        self.music._list.item(0).setSelected(True)
        self.music._remove.click()
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )
        self.register(song)
        self.send("Open a music file.")
        answer = self.answer()
        song.unlink()
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.INVALID
        )
        song = self.song()
        self.send("Open a music file.")
        answer = self.answer()
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )
        self.assertEqual(composition._ControlledAction.created, [])

    def test_expiry_supersession_provider_and_raw_alias_fail_closed(self):
        self.register(self.song())
        self.leases.clock = FakeClock()
        self.send("Open a music file.")
        answer = self.answer()
        for source in (
            ClarificationAnswerSource.PROVIDER,
            ClarificationAnswerSource.LOCAL_TEXT,
            ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT,
        ):
            self.assertIs(
                self.controller.resolve(replace(answer, source=source)).outcome,
                ClarificationOutcome.INVALID,
            )
        self.assertIs(
            self.controller.resolve(
                replace(answer, choice_id=None, value="Song.mp3")
            ).outcome,
            ClarificationOutcome.INVALID,
        )
        self.leases.clock.seconds = self.leases.pending.identity.deadline
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.EXPIRED
        )
        self.send("Open a music file.")
        answer = self.answer()
        self.voice("Open a folder.")
        newer = self.leases.pending.identity
        self.assertIs(
            self.controller.resolve(answer).outcome, ClarificationOutcome.STALE
        )
        self.assertEqual(self.leases.pending.identity, newer)

    def test_settings_open_has_ownership_guard_and_revocation_recheck(self):
        song = self.song()
        self.register(song)
        self.music._list.item(0).setSelected(True)
        self.music._open.click()
        worker = composition._ControlledAction.created[-1]
        self.assertTrue(worker._ownership_guard())
        self.send("Open a folder.")
        self.assertFalse(worker._ownership_guard())
        self.assertTrue(worker._is_cancelled())
        before = len(composition._ControlledAction.created)
        asyncio.run(self.permissions.remove_approved_directory(self.approved.resolve()))
        self.state["open_registered_music"](str(song))
        self.assertEqual(len(composition._ControlledAction.created), before)

    def test_untrusted_text_remote_mixed_and_oversized_drops_are_ignored(self):
        song = self.song()
        for urls in (
            [QUrl("https://example.invalid/music.mp3")],
            [QUrl("file://server/share/music.mp3")],
            [QUrl.fromLocalFile(str(song)), QUrl("https://example.invalid/music.mp3")],
            [QUrl.fromLocalFile(str(song))] * 201,
        ):
            mime = QMimeData()
            mime.setUrls(urls)
            self.assertFalse(self.drop(mime)[0])
        mime = QMimeData()
        mime.setText(str(song))
        self.assertFalse(self.drop(mime)[0])
        self.assertEqual(self.music._config.paths, ())

    def test_save_failure_rolls_back_without_logging_private_exception(self):
        song = self.song("SAVE_SECRET.mp3")
        with (
            patch.object(
                self.state["user_config_store"],
                "save_config",
                side_effect=OSError("SAVE_SECRET private path"),
            ),
            patch.object(self.permissions, "grant_directory", AsyncMock()) as grant,
        ):
            self.register(song)
            grant.assert_not_awaited()
        self.assertEqual(self.music._config.paths, ())
        self.assertEqual(self.settings._config.music_files.paths, ())
        self.assertIn("could not be saved", self.music._status.text())
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        self.assertIn("registration update failed safely", logs)
        self.assertNotIn("SAVE_SECRET", logs)

    def test_restart_config_and_general_settings_save_preserve_registry(self):
        song = self.song()
        self.register(song)
        self.assertTrue(self.settings._save())
        saved = load_config(config_path=self.state["user_config_store"].config_path)
        self.assertEqual(saved.music_files.paths, (str(song),))
        self.settings.update_config(saved)
        self.assertEqual(self.music._list.count(), 1)
        self.send("Open a music file.")
        self.assertEqual(
            tuple(r.parameters["path"] for r in self.leases.pending.choices),
            (str(song),),
        )

    def test_permission_repository_failure_disables_music_choices_safely(self):
        song = self.song("REPOSITORY_SECRET.mp3")
        self.register(song)
        with patch.object(
            self.permissions,
            "get_approved_directories",
            AsyncMock(side_effect=OSError("REPOSITORY_SECRET")),
        ):
            self.send("Open a music file.")
            self.assertEqual(self.leases.pending.local_targets.enabled, (False,))
            self.state["open_registered_music"](str(song))
        self.assertEqual(composition._ControlledAction.created, [])

    def test_registered_paths_and_opaque_answers_do_not_reach_connected_outputs(self):
        album = self.root / "ALBUM_SCOPE_SENTINEL"
        album.mkdir()
        song = album / "MUSIC_PRIVATE_SENTINEL.mp3"
        song.write_bytes(b"synthetic")
        self.register(album)
        ids = []
        for submit in (self.send, self.voice):
            submit("Akiha, please open a music file.")
            ids.extend(self.leases.pending.choice_ids)
            self.send("I prefer MUSIC_PRIVATE_SENTINEL/ Private answer.mp3")
            self.assertEqual(self.chat.messages, ())
            self.assertEqual(self.provider.prompts, [])
            self.panel._submit.click()
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
        with closing(sqlite3.connect(self.state["paths"].database_path)) as connection:
            tables = {
                name: connection.execute('SELECT * FROM "' + name + '"').fetchall()
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertIn("coffee", repr(tables["conversations"]))
        root_tables = [
            name
            for name, rows in tables.items()
            if "ALBUM_SCOPE_SENTINEL" in repr(rows)
        ]
        self.assertEqual(root_tables, ["assistant_action_permissions"])
        del tables["assistant_action_permissions"]
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
        self.assertNotIn("MUSIC_PRIVATE_SENTINEL", surfaces)
        self.assertNotIn("ALBUM_SCOPE_SENTINEL", surfaces)
        for choice_id in ids:
            self.assertNotIn(choice_id, surfaces)
        self.assertIn(
            "MUSIC_PRIVATE_SENTINEL",
            self.state["user_config_store"].config_path.read_text(encoding="utf-8"),
        )

    def test_file_drop_automatically_grants_only_its_containing_folder_open_scope(self):
        folder = self.root / "Handpicked"
        folder.mkdir()
        song = folder / "Selected.mp3"
        song.write_bytes(b"synthetic")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(song))])
        self.assertTrue(self.drop(mime)[1])
        grants = asyncio.run(self.permissions.get_active_permissions())
        self.assertTrue(
            any(
                g.capability == FILE_OPEN_CAPABILITY
                and g.target == str(folder.resolve())
                for g in grants
            )
        )
        self.assertFalse(
            any(
                g.target in (str(folder.resolve()), str(self.root.resolve()))
                and g.capability == FILE_SEARCH_CAPABILITY
                for g in grants
            )
        )
        self.assertFalse(any(g.target == str(self.root.resolve()) for g in grants))
        self.assertIn("Ready", self.music._list.item(0).text())
        self.send("Open a music file.")
        self.assertEqual(self.leases.pending.local_targets.enabled, (True,))

    def test_album_folder_drop_registers_subfolders_and_persists_one_open_root(self):
        album = self.root / "Dropped album"
        disc = album / "Disc 2"
        disc.mkdir(parents=True)
        songs = (album / "Track 1.mp3", disc / "Track 2.flac")
        for song in songs:
            song.write_bytes(b"synthetic")
        (album / "cover.jpg").write_bytes(b"synthetic")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(album))])
        self.assertEqual(self.drop(mime), (True, True, Qt.DropAction.CopyAction))
        self.assertEqual(
            set(self.music._config.paths), {str(p.resolve()) for p in songs}
        )
        grants = asyncio.run(self.permissions.get_active_permissions())
        album_grants = [g for g in grants if g.target == str(album.resolve())]
        self.assertEqual([g.capability for g in album_grants], [FILE_OPEN_CAPABILITY])
        self.assertFalse(any(g.target == str(disc.resolve()) for g in grants))
        with closing(sqlite3.connect(self.state["paths"].database_path)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT count(*) FROM assistant_action_permissions "
                    "WHERE target=? AND revoked_at IS NULL",
                    (str(album.resolve()),),
                ).fetchone()[0],
                1,
            )
        self.voice("Open a music file.")
        self.assertEqual(self.leases.pending.local_targets.enabled, (True, True))
        self.assertTrue(all(p.exists() for p in songs))

    def test_add_folder_picker_and_duplicate_drop_preserve_existing_search_grants(self):
        album = self.root / "Picked album"
        album.mkdir()
        (album / "Song.mp3").write_bytes(b"synthetic")
        asyncio.run(self.permissions.grant_directory(FILE_SEARCH_CAPABILITY, album))
        with patch(
            "project_akiha.ui.music_files_panel.QFileDialog.getExistingDirectory",
            return_value=str(album),
        ):
            self.music._add_folder.click()
        self.register(album)
        grants = [
            g
            for g in asyncio.run(self.permissions.get_active_permissions())
            if g.target == str(album.resolve())
        ]
        self.assertEqual(
            {g.capability for g in grants},
            {FILE_OPEN_CAPABILITY, FILE_SEARCH_CAPABILITY},
        )
        self.assertEqual(len(grants), 2)
        self.assertEqual(self.music._list.count(), 1)

    def test_reload_refresh_and_removal_do_not_regrant_revoked_music_permissions(self):
        album = self.root / "Revocable album"
        album.mkdir()
        song = album / "Song.mp3"
        song.write_bytes(b"synthetic")
        self.register(album)
        asyncio.run(self.permissions.remove_approved_directory(album.resolve()))
        saved = load_config(self.state["user_config_store"].config_path)
        self.settings.update_config(saved)
        self.music.refresh()
        self.send("Open a music file.")
        self.assertEqual(self.leases.pending.local_targets.enabled, (False,))
        # A fresh trusted local selection deliberately approves the same folder.
        self.register(album)
        self.send("Open a music file.")
        self.assertEqual(self.leases.pending.local_targets.enabled, (True,))
        self.music._list.item(0).setSelected(True)
        self.music._remove.click()
        self.assertTrue(song.exists())
        self.assertTrue(
            any(
                g.target == str(album.resolve())
                for g in asyncio.run(self.permissions.get_active_permissions())
            )
        )

    def test_empty_unsupported_and_protected_selections_cannot_grant_folders(self):
        empty = self.root / "Empty album"
        empty.mkdir()
        (empty / "archive.zip").write_bytes(b"synthetic")
        (empty / "run.exe").write_bytes(b"synthetic")
        before = asyncio.run(self.permissions.get_active_permissions())
        self.register(empty, empty / "archive.zip", empty / "run.exe")
        self.assertEqual(self.music._config.paths, ())
        self.assertEqual(asyncio.run(self.permissions.get_active_permissions()), before)
        protected = self.root / "Protected album"
        protected.mkdir()
        song = protected / "Song.mp3"
        song.write_bytes(b"synthetic")
        policy = self.state["music_catalog"].path_policy
        with patch.object(policy, "_protected_roots", (protected.resolve(),)):
            self.register(protected, song)
        self.assertEqual(asyncio.run(self.permissions.get_active_permissions()), before)

    def test_partial_permission_failure_retains_references_and_fails_closed_locally(
        self,
    ):
        good, bad = self.root / "Good album", self.root / "Bad album"
        good.mkdir()
        bad.mkdir()
        for album in (good, bad):
            (album / "Song.mp3").write_bytes(b"synthetic")
        original = self.permissions.grant_directory

        async def grant(capability, root):
            if root == str(bad.resolve()):
                raise sqlite3.OperationalError("PERMISSION_FAILURE_SECRET")
            return await original(capability, root)

        with patch.object(self.permissions, "grant_directory", side_effect=grant):
            self.register(good, bad)
        self.assertEqual(len(self.music._config.paths), 2)
        self.assertIn("could not be", self.music._status.text())
        self.send("Open a music file.")
        self.assertEqual(self.leases.pending.local_targets.enabled, (True, False))
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        self.assertNotIn("PERMISSION_FAILURE_SECRET", logs)

    def test_configuration_only_update_cannot_invent_a_local_permission_selection(self):
        from project_akiha.config import MusicFilesConfig

        song = self.song("Unselected.mp3", approved=False)
        before = asyncio.run(self.permissions.get_active_permissions())
        self.state["update_registered_music"](MusicFilesConfig((str(song),)))
        self.assertEqual(self.music._config.paths, ())
        self.assertEqual(asyncio.run(self.permissions.get_active_permissions()), before)


if __name__ == "__main__":
    unittest.main()
