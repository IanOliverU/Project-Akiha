"""Phase 13B continuations and privacy through the complete application graph."""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import sqlite3
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import Mock, patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QThread, Signal
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

from project_akiha.app import main
from project_akiha.core.actions import (
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
    DirectorySearchMatch,
    FileSearchMatch,
)
from project_akiha.core.actions.clarification import (
    LocalSearchOutcome,
    request_fingerprint,
)
from project_akiha.core.actions.path_input import MAX_CLARIFICATION_INPUT
from project_akiha.core.events import EventType
from project_akiha.core.memory.extraction import HeuristicMemoryExtractor
from project_akiha.core.memory.summarization import HeuristicConversationSummarizer
from project_akiha.providers.ai.mock_provider import MockAIProvider
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolKind,
    AssistantToolProposal,
)
from project_akiha.services.intent_arbitration import IntentProposalSource
from project_akiha.services.transcript_export import (
    render_chat_transcript,
    write_chat_transcript,
)
from project_akiha.ui.assistant_action_worker import AssistantActionThread
from project_akiha.ui.assistant_tool_worker import (
    DirectorySearchOutcome,
    MediaSearchOutcome,
)


class _RecordingProvider(MockAIProvider):
    def __init__(self):
        self.prompts = []

    async def generate_response(self, messages):
        self.prompts.append(tuple(messages))
        return "Public composition-test reply."


class _ControlledSearch(QThread):
    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    created = []

    def __init__(self, *args):
        super().__init__()
        self.start = Mock()
        self.created.append(self)

    def cancel(self):
        self.cancelled.emit()


class _ControlledAction(AssistantActionThread):
    created = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start = Mock()
        self.created.append(self)


class _StartupCaptured(BaseException):
    pass


class Phase13BCompositionTest(unittest.TestCase):
    """Only external transport and asynchronous delivery are controlled doubles."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = {}
        self.startup_context = QObject()
        self.provider = _RecordingProvider()
        self.old_services = getattr(self.app, "_akiha_services", ())
        self.logger = logging.getLogger("project_akiha")
        self.old_handlers = tuple(self.logger.handlers)
        self.old_log_level, self.old_propagate = (
            self.logger.level,
            self.logger.propagate,
        )
        _ControlledSearch.created = []
        _ControlledAction.created = []
        self.addCleanup(self.release_graph)
        tree = ast.parse(Path(main.__file__).read_text(encoding="utf-8"))
        return_line = next(
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Return)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "exec"
        )

        def capture(frame, event, arg):
            if (
                frame.f_code is main._run_application.__code__
                and event == "line"
                and frame.f_lineno == return_line
            ):
                self.state.update(frame.f_locals)
                raise _StartupCaptured()
            return capture

        single_shot = main.QTimer.singleShot
        with (
            patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)}),
            patch.object(main, "QApplication", lambda *_: self.app),
            patch.object(main, "privacy_notice_required", lambda *_: False),
            patch.object(main, "_build_ai_provider", lambda *_: self.provider),
            # Give delayed startup callbacks the lifetime of this graph. They
            # run normally while it exists, and Qt cancels them on destruction.
            patch.object(
                main.QTimer,
                "singleShot",
                lambda delay, callback: single_shot(
                    delay, self.startup_context, callback
                ),
            ),
        ):
            old_trace = sys.gettrace()
            sys.settrace(capture)
            try:
                main._run_application()
            except _StartupCaptured:
                pass
            finally:
                sys.settrace(old_trace)
        self.assertTrue(self.state, "must build the actual application composition")
        # Drain production startup single-shots while their widgets are alive;
        # no initialization closure may spill into the next composed graph.
        self.app.processEvents()
        self.controller = self.state["action_clarification"]
        self.leases = self.controller.leases
        self.window = self.state["chat_window"]
        self.chat = self.state["chat_controller"]
        self.chat.set_ai_provider(self.provider)
        self.chat.set_memory_enabled(True)
        self.chat.set_memory_requires_approval(False)
        self.state["memory_pipeline"].set_extractor(HeuristicMemoryExtractor())
        self.chat.set_conversation_summarizer(HeuristicConversationSummarizer())
        self.events = []
        for kind in EventType:
            self.state["event_bus"].subscribe(kind, self.events.append)
        self.approved = self.root / "Approved"
        self.approved.mkdir()
        permissions = self.state["assistant_permission_service"]
        for capability in (FILE_SEARCH_CAPABILITY, FILE_OPEN_CAPABILITY):
            asyncio.run(permissions.grant_directory(capability, self.approved))
        for name, replacement in (
            ("AssistantDirectorySearchThread", _ControlledSearch),
            ("AssistantMediaSearchThread", _ControlledSearch),
            ("AssistantActionThread", _ControlledAction),
        ):
            patcher = patch.object(main, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def release_graph(self):
        if self.state:
            self.app.processEvents()
            self.state["shutdown_app"]()
            self.app.processEvents()
            self.state["instance_coordinator"].close()
            self.app.aboutToQuit.disconnect(self.state["shutdown_app"])
        self.app._akiha_services = self.old_services
        self.startup_context.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        objects = [v for v in self.state.values() if isinstance(v, QObject)]
        objects.extend(_ControlledSearch.created + _ControlledAction.created)
        for obj in objects:
            if obj is self.app or not isValid(obj):
                continue
            if isinstance(obj, QThread):
                obj.requestInterruption()
                self.assertTrue(obj.wait(2000))
            if hasattr(obj, "close"):
                obj.close()
            obj.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.state.clear()
        _ControlledSearch.created.clear()
        _ControlledAction.created.clear()
        for handler in tuple(self.logger.handlers):
            if handler not in self.old_handlers:
                self.logger.removeHandler(handler)
                handler.close()
        self.logger.setLevel(self.old_log_level)
        self.logger.propagate = self.old_propagate
        self.temp.cleanup()

    def send(self, text):
        self.window._input.setText(text)
        self.window._submit_message()
        self.wait_chat()

    def wait_chat(self):
        limit = time.monotonic() + 5
        while self.state["active_chat_threads"] and time.monotonic() < limit:
            self.app.processEvents()
            time.sleep(0.001)
        self.app.processEvents()
        self.assertEqual(self.state["active_chat_threads"], [])
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def search(self, directory):
        proposal = (
            AssistantToolProposal(
                AssistantToolKind.OPEN_DIRECTORY, directory_name="folder"
            )
            if directory
            else AssistantToolProposal(
                AssistantToolKind.PLAY_MEDIA, title="song", artist="public artist"
            )
        )
        turn_id = "composition-" + uuid4().hex
        self.state["intent_arbiter"].complete_local_routing(turn_id)
        self.state["start_directory_search" if directory else "start_media_search"](
            proposal,
            turn_id=turn_id,
            source=IntentProposalSource.PROVIDER,
        )
        worker = _ControlledSearch.created[-1]
        # This is the authority installed by the real composition callback setup.
        return worker, self.leases._local_search

    def outcome(self, directory, count, *, limited=False, complete=True):
        matches = tuple(
            (
                DirectorySearchMatch(
                    f"folder{i}", str(self.approved / f"folder{i}"), "now"
                )
                if directory
                else FileSearchMatch(
                    f"song{i}", str(self.approved / f"song{i}.mp3"), 1, "now"
                )
            )
            for i in range(count)
        )
        return (DirectorySearchOutcome if directory else MediaSearchOutcome)(
            matches, 1, complete, limited
        )

    def test_zero_multiple_limited_and_unique_share_captured_ownership(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                with self.subTest(directory=directory, count=count, limited=limited):
                    worker, identity = self.search(directory)
                    old_actions = len(_ControlledAction.created)
                    worker.result_ready.emit(
                        self.outcome(directory, count, limited=limited)
                    )
                    self.assertEqual(self.leases.owner_epoch, identity.owner_epoch)
                    if count == 1 and not limited:
                        action = _ControlledAction.created[-1]
                        self.assertEqual(
                            len(_ControlledAction.created), old_actions + 1
                        )
                        self.assertEqual(
                            action._request.correlation_id, identity.request_id
                        )
                        self.assertEqual(action._request.action_id, identity.operation)
                        self.assertTrue(action._ownership_guard())
                    else:
                        self.assertEqual(len(_ControlledAction.created), old_actions)
                        pending = self.leases.pending
                        self.assertEqual(
                            pending.request.correlation_id, identity.request_id
                        )
                        self.assertEqual(
                            pending.identity.owner_epoch, identity.owner_epoch
                        )
                        self.assertEqual(len(pending.choices), count)
                        self.assertEqual(pending.spec.truncated, limited)

    def barrier_supersession(self, worker, outcome, *, boundary):
        barrier = Barrier(2)
        method = (
            self.leases.continue_local_search
            if boundary != "enqueue"
            else self.leases.enqueue_local_search
        )
        newer = []

        def accept_new():
            barrier.wait(5)
            self.state["submit_chat_message"]("please open app")
            newer.append(self.leases.pending)
            barrier.wait(5)

        def blocked(*args, **kwargs):
            if boundary == "after_publication":
                result = method(*args, **kwargs)
            barrier.wait(5)
            barrier.wait(5)
            return (
                result if boundary == "after_publication" else method(*args, **kwargs)
            )

        name = (
            "enqueue_local_search" if boundary == "enqueue" else "continue_local_search"
        )
        with (
            ThreadPoolExecutor(max_workers=1) as pool,
            patch.object(self.leases, name, blocked),
        ):
            future = pool.submit(accept_new)
            worker.result_ready.emit(outcome)
            future.result(5)
        self.app.processEvents()
        self.assertEqual(self.leases.pending, newer[0])
        self.assertEqual(self.leases.pending.request.action_id, "applications.launch")

    def test_barrier_supersession_before_publication_all_result_shapes(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                with self.subTest(directory=directory, count=count, limited=limited):
                    worker, _ = self.search(directory)
                    before = len(_ControlledAction.created)
                    self.barrier_supersession(
                        worker,
                        self.outcome(directory, count, limited=limited),
                        boundary="before_publication",
                    )
                    self.assertEqual(len(_ControlledAction.created), before)

    def test_barrier_supersession_after_publication_all_result_shapes(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                with self.subTest(directory=directory, count=count, limited=limited):
                    worker, _ = self.search(directory)
                    before = len(_ControlledAction.created)
                    self.barrier_supersession(
                        worker,
                        self.outcome(directory, count, limited=limited),
                        boundary="after_publication",
                    )
                    self.assertEqual(len(_ControlledAction.created), before)

    def test_barrier_supersession_immediately_before_execution_enqueue(self):
        for directory in (False, True):
            worker, _ = self.search(directory)
            before = len(_ControlledAction.created)
            self.barrier_supersession(
                worker, self.outcome(directory, 1), boundary="enqueue"
            )
            self.assertEqual(len(_ControlledAction.created), before)

    def test_reentrant_supersession_during_suspension_hook(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True)):
                worker, _ = self.search(directory)
                old_hook = self.controller.before_pending
                newer = []

                def interleave(newer=newer):
                    self.controller.before_pending = None
                    self.state["submit_chat_message"]("please open app")
                    newer.append(self.leases.pending)
                    return False

                try:
                    self.controller.before_pending = interleave
                    worker.result_ready.emit(
                        self.outcome(directory, count, limited=limited)
                    )
                finally:
                    self.controller.before_pending = old_hook
                self.assertEqual(self.leases.pending, newer[0])

    def test_revocation_during_search_rejects_every_result_shape(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                for capability in (FILE_SEARCH_CAPABILITY, FILE_OPEN_CAPABILITY):
                    asyncio.run(
                        self.state["assistant_permission_service"].grant_directory(
                            capability, self.approved
                        )
                    )
                worker, _ = self.search(directory)
                before = len(_ControlledAction.created)
                asyncio.run(
                    self.state[
                        "assistant_permission_service"
                    ].remove_approved_directory(self.approved)
                )
                worker.result_ready.emit(
                    self.outcome(directory, count, limited=limited)
                )
                self.assertIsNone(self.leases.pending)
                self.assertEqual(len(_ControlledAction.created), before)

    def test_cancellation_during_search_rejects_every_result_shape(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                worker, _ = self.search(directory)
                before = len(_ControlledAction.created)
                worker.cancelled.emit()
                worker.result_ready.emit(
                    self.outcome(directory, count, limited=limited)
                )
                self.assertIsNone(self.leases.pending)
                self.assertEqual(len(_ControlledAction.created), before)

    def test_duplicate_and_late_results_and_failures_cannot_change_state(self):
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                worker, _ = self.search(directory)
                result = self.outcome(directory, count, limited=limited)
                worker.result_ready.emit(result)
                pending = self.leases.pending
                before = len(_ControlledAction.created)
                worker.result_ready.emit(result)
                worker.failed.emit("COMP_SECRET/private error")
                worker.cancelled.emit()
                self.assertEqual(self.leases.pending, pending)
                self.assertEqual(len(_ControlledAction.created), before)
                self.assertNotIn("COMP_SECRET", self.window._history_view.toPlainText())

    def test_exact_search_timeout_boundaries_for_all_shapes(self):
        now = [10.0]
        self.leases.clock = type("Clock", (), {"monotonic_seconds": lambda _: now[0]})()
        for directory in (False, True):
            for count, limited in ((0, False), (2, False), (1, True), (1, False)):
                for offset in (-0.000001, 0, 0.000001):
                    worker, identity = self.search(directory)
                    before = len(_ControlledAction.created)
                    now[0] = identity.deadline + offset
                    worker.result_ready.emit(
                        self.outcome(directory, count, limited=limited)
                    )
                    if offset < 0:
                        self.assertTrue(
                            self.leases.pending is not None
                            or len(_ControlledAction.created) > before
                        )
                    else:
                        self.assertIsNone(self.leases.pending)
                        self.assertEqual(len(_ControlledAction.created), before)

    def test_complete_fingerprint_generation_nonce_and_creation_are_bound(self):
        for directory in (False, True):
            _, identity = self.search(directory)
            self.assertEqual(
                identity.request_digest, request_fingerprint(identity.request)
            )
            for field, value in (
                ("owner_epoch", 999),
                ("request_digest", "0" * 64),
                ("request_id", "wrong"),
                ("action_id", "files.search"),
                ("source", "chat"),
                ("operation", "files.search"),
                ("generation", 999),
                ("nonce", "wrong"),
                ("creation_id", "wrong"),
                ("created_at", 999),
                ("deadline", 999),
            ):
                result = self.leases.continue_local_search(
                    replace(identity, **{field: value}), ()
                )
                self.assertEqual(result.outcome, LocalSearchOutcome.STALE)
            changed = replace(
                identity.request,
                parameters={**identity.request.parameters, "title": "different"},
            )
            with self.assertRaises(ValueError):
                self.leases.claim(changed)
            self.assertEqual(
                self.leases.continue_local_search(identity, ()).outcome,
                LocalSearchOutcome.STALE,
            )

    def test_ready_admission_is_single_use_and_expires_before_enqueue(self):
        now = [10.0]
        self.leases.clock = type("Clock", (), {"monotonic_seconds": lambda _: now[0]})()
        for directory in (False, True):
            for expire in (False, True):
                _, identity = self.search(directory)
                ready = self.leases.continue_local_search(
                    identity, (str(self.approved / "song.mp3"),)
                )
                enqueue = Mock()
                if expire:
                    now[0] = identity.deadline
                self.assertEqual(
                    self.leases.enqueue_local_search(ready, enqueue), not expire
                )
                self.assertFalse(self.leases.enqueue_local_search(ready, enqueue))
                self.assertEqual(enqueue.call_count, int(not expire))

    def test_worker_rechecks_owner_before_dispatching_queued_unique_result(self):
        for directory in (False, True):
            worker, _ = self.search(directory)
            worker.result_ready.emit(self.outcome(directory, 1))
            action = _ControlledAction.created[-1]
            dispatch = Mock()
            with patch.object(action, "_dispatch", dispatch):
                self.send("please open app")
                action.run()
                dispatch.assert_not_called()

    def test_rejected_result_is_typed_and_cannot_be_replayed(self):
        for directory in (False, True):
            for paths in (("",), ("bad\x00path", "other"), ("x" * 5000,)):
                with self.subTest(directory=directory, paths=len(paths)):
                    _, identity = self.search(directory)
                    result = self.leases.continue_local_search(identity, paths)
                    self.assertEqual(result.outcome, LocalSearchOutcome.REJECTED)
                    self.assertEqual(
                        self.leases.continue_local_search(identity, ()).outcome,
                        LocalSearchOutcome.STALE,
                    )

    def test_connected_privacy_rejects_all_material_on_every_real_surface(self):
        deep = "%2FCOMP_SECRET.mp3"
        encoded = []
        for _ in range(20):
            deep = deep.replace("%", "%25")
            encoded.append("I prefer " + deep)
        material = [
            "I prefer Downloads/ COMP_SECRET.mp3",
            "I prefer %2525252FCOMP_SECRET.mp3",
            "the path is /home/private/COMP_SECRET.mp3",
            r"I prefer C:\Private Folder\COMP_SECRET.mp3",
            r"I prefer \\server\Private Folder\COMP_SECRET.mp3",
            r"Downloads/ Private Folder\COMP_SECRET.mp3",
            'the path is "Downloads/ Private Folder/COMP_SECRET.mp3"',
            "I prefer file:///home/private/COMP_SECRET.mp3",
            "I prefer Downloads%2F Private Folder/COMP_SECRET.mp3",
            "I prefer Downloads/ Private%5C COMP_SECRET.mp3",
            "I prefer %2e%2e COMP_SECRET.mp3",
            "I prefer %ZZCOMP_SECRET.mp3",
            "I prefer %2COMP_SECRET.mp3",
            "I prefer %C0%AFCOMP_SECRET.mp3",
            "I prefer %u2215COMP_SECRET.mp3",
            "I prefer Downloads\u200b/\u00a0COMP_SECRET.mp3",
            "I prefer Downloads\u2215 COMP_SECRET.mp3",
            "I prefer \uff05\uff12\uff26COMP_SECRET.mp3",
            "COMP_SECRET" + "x" * MAX_CLARIFICATION_INPUT,
        ] + encoded
        for command in ("please open file", "please open folder"):
            self.send(command)
            owner = self.leases.pending.identity
            for text in material:
                self.send(text)
                self.assertEqual(self.leases.pending.identity, owner)
                self.assertEqual(self.chat.messages, ())
                self.assertEqual(self.provider.prompts, [])
                self.assertNotIn(
                    "COMP_SECRET", self.state["clarification_panel"]._label.text()
                )
        self.send("I prefer public coffee with oat milk.")
        self.assertTrue(
            asyncio.run(self.state["memory_repository"].get_recent_memories(100))
        )
        exported = render_chat_transcript(
            asyncio.run(self.chat.get_export_messages()), assistant_name="Akiha"
        )
        export_path = self.root / "history.txt"
        write_chat_transcript(export_path, exported)
        prompts = asyncio.run(self.chat.build_provider_messages("public followup"))
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
        self.assertTrue(
            any(
                e.event_type is EventType.PROACTIVE_SUGGESTION_DELIVERED
                for e in self.events
            )
        )
        with closing(sqlite3.connect(self.state["paths"].database_path)) as connection:
            tables = {
                name: connection.execute('SELECT * FROM "' + name + '"').fetchall()
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        logs = "\n".join(
            p.read_text(encoding="utf-8") for p in self.root.rglob("*.log")
        )
        self.assertIn("proactive.suggestion_delivered", logs)
        self.assertIn("coffee", repr(tables["conversations"]))
        surfaces = [
            self.window._history_view.toPlainText(),
            repr(self.chat.messages),
            repr(self.provider.prompts),
            repr(prompts),
            repr(tables),
            export_path.read_text(encoding="utf-8"),
            repr(self.events),
            logs,
            repr(asyncio.run(self.state["memory_repository"].get_recent_memories(100))),
        ]
        self.assertNotIn("COMP_SECRET", "\n".join(surfaces))

    def test_trusted_local_button_sends_only_current_composer_as_chat(self):
        self.send("please open file")
        owner = self.leases.pending.identity
        self.send("Discuss Downloads/ PUBLIC_DISCUSSION.mp3")
        self.assertEqual(self.provider.prompts, [])
        self.window._input.setText("Discuss Downloads/ PUBLIC_DISCUSSION.mp3")
        self.state["clarification_panel"]._normal_chat.click()
        self.wait_chat()
        self.assertEqual(self.leases.pending.identity, owner)
        self.assertIn("PUBLIC_DISCUSSION", repr(self.provider.prompts))
        self.assertEqual(_ControlledAction.created, [])
        # The explicit action never arms a later provider/voice/composer bypass.
        count = len(self.chat.messages)
        self.send("I prefer Downloads/ COMP_SECRET.mp3")
        self.assertEqual(len(self.chat.messages), count)

    def test_stale_normal_chat_button_cannot_override_new_owner(self):
        self.send("please open file")
        old = self.leases.pending.identity
        self.send("please open folder")
        self.window._input.setText("I prefer Downloads/ COMP_SECRET.mp3")
        self.state["clarification_panel"].normal_chat_requested.emit(old)
        self.wait_chat()
        self.assertEqual(self.provider.prompts, [])
        self.assertEqual(self.chat.messages, ())
