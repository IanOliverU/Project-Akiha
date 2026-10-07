"""Independent regressions for the Phase 13B audit's acceptance failures."""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QObject, Signal
from PySide6.QtWidgets import QApplication

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.app.chat_controller import ChatController
from project_akiha.app.hosted_conversation_runtime import HostedConversationRuntime
from project_akiha.app.integration_notification_coordinator import (
    IntegrationNotificationCoordinator,
)
from project_akiha.app.proactive_delivery_controller import ProactiveDeliveryController
from project_akiha.config import BehaviorConfig, ExternalIntegrationsConfig
from project_akiha.core.actions import (
    ActionRequest,
    ActionResult,
    ActionStatus,
    FileSearchMatch,
    PermissionDecision,
    build_default_provider_action_catalog,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.core.actions.path_input import looks_like_private_path
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
    ProactiveDeliveryService,
)
from project_akiha.core.events import EventBus, EventType
from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.core.memory import MemoryPipeline
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import ActionProposal, SessionLifecycle
from project_akiha.database.sqlite_conversation_repository import (
    SQLiteConversationRepository,
)
from project_akiha.database.sqlite_external_event_repository import (
    SQLiteExternalEventRepository,
)
from project_akiha.database.sqlite_memory_repository import SQLiteMemoryRepository
from project_akiha.database.sqlite_notification_repository import (
    SQLiteNotificationRepository,
)
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.assistant_tool_gateway import (
    parse_directory_navigation_proposal,
)
from project_akiha.services.ephemeral_action_context import (
    EphemeralDirectoryReference,
    EphemeralReferenceError,
    EphemeralSelectionReference,
)
from project_akiha.services.event_logger import EventLogger
from project_akiha.services.external_event_validation import ExternalEventValidator
from project_akiha.services.external_notification_renderer import (
    ExternalNotificationRenderer,
)
from project_akiha.services.intent_arbitration import IntentProposalSource
from project_akiha.services.provider_action_proposal_gateway import (
    ProviderActionProposalGateway,
)
from project_akiha.services.transcript_export import (
    render_chat_transcript,
    write_chat_transcript,
)
from project_akiha.ui.action_clarification_panel import ActionClarificationPanel
from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.proactive_delivery import QtProactiveDeliverySurface
from tests.unit.app.test_chat_controller import StaticProvider
from tests.unit.services.test_action_clarification import FakeClock
from tests.unit.ui import test_phase13b_proposal_flows as flows
from tests.unit.ui.test_hosted_live_session_worker import _frame


class CorrectionOwnershipTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.leases = ActionClarificationService(clock=self.clock)
        self.controller = ActionClarificationController(self.leases)

    def test_barrier_new_action_wins_between_owner_check_and_publication(self):
        old = ActionRequest(
            "old",
            "files.search",
            "chat",
            {"root": "C:/Approved", "query": "song", "result_mode": "open_unique"},
        )
        self.controller.prepare(old)
        epoch = self.leases.owner_epoch
        confirmation = self.leases.issue_confirmation(old, owner_epoch=epoch)
        result = ActionResult(
            "old",
            "files.search",
            ActionStatus.SUCCESS,
            "fixture",
            PermissionDecision.GRANTED,
            metadata={
                "matches": (FileSearchMatch("song", "C:/Approved/song.mp3", 1, "now"),)
            },
        )
        barrier = Barrier(2)
        owns = self.leases.owns
        checked = False

        def pause_after_check(request, owner_epoch=None):
            nonlocal checked
            accepted = owns(request, owner_epoch)
            if not checked:
                checked = True
                barrier.wait(timeout=5)
                barrier.wait(timeout=5)
            return accepted

        self.leases.owns = pause_after_check
        suspend = Mock(return_value=False)
        self.controller.before_pending = suspend
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                self.controller.handle_local_result, old, result, owner_epoch=epoch
            )
            barrier.wait(timeout=5)
            self.controller.prepare(
                ActionRequest("new", "applications.launch", "chat", {})
            )
            newer = self.leases.pending
            suspend.reset_mock()
            barrier.wait(timeout=5)
            self.assertTrue(future.result(timeout=5))
        self.leases.owns = owns
        self.assertEqual(self.leases.pending, newer)
        suspend.assert_not_called()
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, old, approved=True)
        )
        with self.assertRaises(ValueError):
            self.leases.issue_confirmation(old, owner_epoch=epoch)

    def test_atomic_publication_requires_exact_request_identity(self):
        owner = ActionRequest("owner", "files.open", "chat", {"path": "C:/Approved/a"})
        self.controller.prepare(owner)
        epoch = self.leases.owner_epoch
        self.controller.prepare(ActionRequest("new", "files.open", "chat", {}))
        newer = self.leases.pending
        changed = replace(owner, parameters={"path": "C:/Approved/b"})
        for request, captured_epoch in (
            (owner, epoch),
            (changed, self.leases.owner_epoch),
        ):
            with self.assertRaises(ValueError):
                self.leases.publish_result(request, captured_epoch, owner, newer.spec)
            self.assertEqual(self.leases.pending, newer)
        # The pre-publication audio hook can deliver synchronous application
        # events. A new explicit request accepted reentrantly must also win.
        leases = ActionClarificationService()
        controller = ActionClarificationController(leases)
        controller.prepare(owner)
        epoch = leases.owner_epoch

        def accept_new_during_audio_pause():
            controller.prepare(newer.request)
            return False

        with self.assertRaises(ValueError):
            leases.publish_result(
                owner,
                epoch,
                owner,
                newer.spec,
                before_publish=accept_new_during_audio_pause,
            )
        self.assertEqual(leases.pending.request, newer.request)

    def test_incomplete_action_advances_epoch_and_invalidates_old_confirmation(self):
        old = ActionRequest("old", "files.open", "chat", {"path": "C:/Approved/a.mp3"})
        self.controller.prepare(old)
        confirmation = self.leases.issue_confirmation(old)
        epoch = self.leases.owner_epoch
        self.controller.prepare(ActionRequest("new", "applications.launch", "chat", {}))
        self.assertGreater(self.leases.owner_epoch, epoch)
        self.assertFalse(
            self.leases.consume_confirmation(confirmation, old, approved=True)
        )
        self.assertEqual(self.leases.pending.request.correlation_id, "new")

    def test_old_search_result_never_replaces_new_pending_action(self):
        old = ActionRequest(
            "old",
            "files.search",
            "chat",
            {"root": "C:/Approved", "query": "song", "result_mode": "open_unique"},
        )
        self.controller.prepare(old)
        self.controller.prepare(ActionRequest("new", "applications.launch", "chat", {}))
        newer = self.leases.pending
        result = ActionResult(
            "old",
            "files.search",
            ActionStatus.SUCCESS,
            "fixture",
            permission_decision=PermissionDecision.GRANTED,
            metadata={
                "matches": (
                    FileSearchMatch("song.mp3", "C:/Approved/song.mp3", 1, "now"),
                )
            },
        )
        self.assertTrue(self.controller.handle_local_result(old, result))
        self.assertEqual(self.leases.pending, newer)

    def test_same_id_changed_fields_fail_closed_even_after_resolution(self):
        original = ActionRequest("same", "files.search", "chat", {"root": "C:/One"})
        for changed in (
            replace(original, parameters={"root": "C:/Two"}),
            replace(original, action_id="directories.search"),
            replace(original, source="provider.gemini.live"),
        ):
            with self.subTest(changed=changed):
                leases = ActionClarificationService()
                controller = ActionClarificationController(leases)
                controller.prepare(original)
                old = leases.pending
                self.assertFalse(controller.prepare(changed))
                self.assertIsNone(leases.pending)
                self.assertEqual(
                    leases.resolve(
                        ClarificationAnswer(
                            old.identity, ClarificationAnswerSource.LOCAL_UI, "song"
                        )
                    ).outcome,
                    ClarificationOutcome.STALE,
                )
        self.controller.prepare(original)
        pending = self.leases.pending
        resolved = self.controller.resolve(
            ClarificationAnswer(
                pending.identity, ClarificationAnswerSource.LOCAL_UI, "song"
            )
        )
        self.assertEqual(resolved.outcome, ClarificationOutcome.RESOLVED)
        self.assertTrue(self.controller.prepare(resolved.request))
        self.assertFalse(
            self.controller.prepare(
                replace(
                    resolved.request, parameters={"root": "C:/Two", "query": "song"}
                )
            )
        )

    def test_identical_normalized_repeat_and_unrelated_chat_keep_deadline(self):
        request = ActionRequest("same", "files.search", "chat", {"root": "C:/One"})
        self.controller.prepare(request)
        old = self.leases.pending
        self.clock.seconds += 100
        self.controller.prepare(replace(request, parameters={"root": "  C:/One  "}))
        self.assertEqual(self.leases.pending.identity, old.identity)
        for text in (
            "How are you?",
            "I like music",
            "Discuss paths and folders",
        ):
            self.assertIsNone(self.controller.route_answer(text))
            self.assertEqual(self.leases.pending.identity, old.identity)
        # Path discussion during a file clarification requires the deliberate
        # trusted-local normal-chat control, including slash-shaped examples.
        for text in (
            "What does A/B testing mean?",
            "I found https://example.com/music helpful.",
        ):
            self.assertEqual(
                self.controller.route_answer(text).outcome, ClarificationOutcome.INVALID
            )
            self.assertEqual(self.leases.pending.identity, old.identity)

    def test_exact_boundaries_for_both_leases(self):
        for offset, expected in ((-0.000001, True), (0, False), (0.000001, False)):
            with self.subTest(offset=offset):
                clock = FakeClock()
                leases = ActionClarificationService(clock=clock)
                controller = ActionClarificationController(leases)
                controller.prepare(
                    ActionRequest("boundary", "applications.launch", "chat", {})
                )
                pending = leases.pending
                clock.seconds = pending.identity.deadline + offset
                result = leases.resolve(
                    ClarificationAnswer(
                        pending.identity, ClarificationAnswerSource.LOCAL_UI, "spotify"
                    )
                )
                self.assertEqual(
                    result.outcome is ClarificationOutcome.RESOLVED, expected
                )
                request = ActionRequest(
                    "confirmation", "files.open", "chat", {"path": "C:/Approved/a.mp3"}
                )
                lease = leases.issue_confirmation(request)
                clock.seconds = lease.deadline + offset
                self.assertEqual(
                    leases.consume_confirmation(lease, request, approved=True), expected
                )
                self.assertFalse(
                    leases.consume_confirmation(lease, request, approved=True)
                )

    def test_synchronized_double_submission_has_one_winner(self):
        for kind in ("clarification", "confirmation"):
            with self.subTest(kind=kind):
                leases = ActionClarificationService()
                controller = ActionClarificationController(leases)
                request = ActionRequest("race", "applications.launch", "chat", {})
                controller.prepare(request)
                answer = ClarificationAnswer(
                    leases.pending.identity,
                    ClarificationAnswerSource.LOCAL_UI,
                    "spotify",
                )
                confirmation_request = replace(
                    request, parameters={"application_id": "spotify"}
                )
                lease = leases.issue_confirmation(confirmation_request)
                barrier = Barrier(8)

                def submit(
                    _,
                    barrier=barrier,
                    kind=kind,
                    leases=leases,
                    answer=answer,
                    lease=lease,
                    confirmation_request=confirmation_request,
                ):
                    barrier.wait()
                    if kind == "clarification":
                        return (
                            leases.resolve(answer).outcome
                            is ClarificationOutcome.RESOLVED
                        )
                    return leases.consume_confirmation(
                        lease, confirmation_request, approved=True
                    )

                with ThreadPoolExecutor(max_workers=8) as pool:
                    self.assertEqual(sum(pool.map(submit, range(8))), 1)

    def test_newer_action_wins_during_delayed_question_preparation(self):
        entered, release = Event(), Event()

        def before_question():
            entered.set()
            self.assertTrue(release.wait(3))
            return False

        self.controller.before_pending = before_question
        with ThreadPoolExecutor(max_workers=1) as pool:
            old = pool.submit(
                self.controller.prepare, ActionRequest("old", "files.open", "chat", {})
            )
            self.assertTrue(entered.wait(3))
            self.controller.prepare(
                ActionRequest(
                    "new", "applications.launch", "chat", {"application_id": "spotify"}
                )
            )
            epoch = self.leases.owner_epoch
            release.set()
            self.assertFalse(old.result(timeout=3))
        self.assertEqual(self.leases.owner_epoch, epoch)
        self.assertIsNone(self.leases.pending)

    def test_late_confirmation_issuance_and_candidate_publication_fail_closed(self):
        old = ActionRequest("old", "files.open", "chat", {"path": "C:/Approved/a.mp3"})
        self.controller.prepare(old)
        epoch = self.leases.owner_epoch
        self.controller.prepare(ActionRequest("new", "applications.launch", "chat", {}))
        newer = self.leases.pending
        with self.assertRaises(ValueError):
            self.leases.issue_confirmation(old, owner_epoch=epoch)
        with self.assertRaises(ValueError):
            self.controller.choices(old, (), owner_epoch=epoch)
        self.assertEqual(self.leases.pending, newer)

    def test_dispatcher_rejects_late_search_and_confirmation_results(self):
        async def probe(status):
            fixture = flows.Phase13BProposalFlowTest()
            fixture.setUp()
            worker, turn, service, gateway, _ = fixture.hosted()
            entered, release = asyncio.Event(), asyncio.Event()

            async def evaluate(request, **kwargs):
                entered.set()
                await release.wait()
                return ActionResult(
                    request.correlation_id,
                    request.action_id,
                    status,
                    "fixture",
                    permission_decision=PermissionDecision.GRANTED,
                    metadata={
                        "matches": (
                            FileSearchMatch(
                                "song.mp3", "C:/Approved/song.mp3", 1, "now"
                            ),
                        )
                    },
                )

            service.evaluate_request = evaluate
            proposal = ActionProposal(
                turn.session_id,
                turn.turn_id,
                "late",
                "gemini.live",
                "applications.launch",
                {"application_id": "spotify"},
            )
            conversion = gateway.convert(proposal)
            dispatcher = worker._action_dispatcher
            dispatcher.complete_local_routing(turn.session_id, turn.turn_id)
            presented = Mock()
            task = asyncio.create_task(
                dispatcher.dispatch(conversion, on_local_result=presented)
            )
            await entered.wait()
            fixture.controller.prepare(
                ActionRequest("new-owner", "files.open", "chat", {})
            )
            newer = fixture.leases.pending
            release.set()
            result = await task
            self.assertEqual(result.status, "cancelled")
            self.assertEqual(fixture.leases.pending, newer)
            self.assertEqual(dispatcher.pending_confirmation_count, 0)
            presented.assert_not_called()

        for status in (ActionStatus.SUCCESS, ActionStatus.CONFIRMATION_REQUIRED):
            with self.subTest(status=status):
                asyncio.run(probe(status))


PATH_REPLIES = (
    "Downloads/Private Folder/SECRET123.mp3",
    "the path is /home/private/SECRET123.mp3",
    "I prefer /home/private/SECRET123.mp3",
    'the path is "Downloads/Private Folder/SECRET123.mp3"',
    "My Downloads/Private Folder/SECRET123.mp3",
    r"the path is C:\Private Folder\SECRET123.mp3",
    r"I prefer \\server\Private Folder\SECRET123.mp3",
    "the path is file:///home/private/SECRET123.mp3",
    "I prefer %2Fhome%2Fprivate%2FSECRET123.mp3",
    r"Downloads/Private Folder\SECRET123.mp3",
    "C:/Private/SECRET123.mp3",
    "C:Private\\SECRET123.mp3",
    "\\\\server\\share\\SECRET123.mp3",
    "/home/Alice/SECRET123.mp3",
    "\\Private/SECRET123.mp3",
    "file:///C:/Private/SECRET123.mp3",
    "%43%3A%5CPrivate%5CSECRET123.mp3",
    "%252Fhome%252FAlice%252FSECRET123.mp3",
    "Ｃ：／Private／SECRET123.mp3",
    '"/home/Alice/SECRET123.mp3"',
    "../Private/SECRET123.mp3",
    "~/Private/SECRET123.mp3",
    "Downloads/Private/SECRET123.mp3",
    "%EF%BC%A3%EF%BC%9A%EF%BC%8FSECRET123.mp3",
    "\u200bC:/Private/SECRET123.mp3",
)


class CorrectionConnectedPrivacyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_actual_composer_panel_provider_export_and_sqlite_are_connected(self):
        # Execute the unchanged production closure body with real privacy surfaces.
        # The app's full startup would open accounts/devices and personal state.
        main_path = Path(__file__).resolve().parents[3] / "project_akiha/app/main.py"
        tree = ast.parse(main_path.read_text(encoding="utf-8"))
        body = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "submit_chat_message"
        )
        with TemporaryDirectory() as temp:
            db = Path(temp) / "audit.sqlite3"
            repo = SQLiteConversationRepository(db)
            conversation = asyncio.run(repo.create_conversation())
            provider = StaticProvider("ordinary reply")
            logged = []

            class Recorder(logging.Handler):
                def emit(self, record):
                    logged.append(record.getMessage())

            handler = Recorder()
            app_logger = logging.getLogger("project_akiha")
            app_logger.addHandler(handler)
            self.addCleanup(app_logger.removeHandler, handler)
            old_level = app_logger.level
            app_logger.setLevel(logging.INFO)
            self.addCleanup(app_logger.setLevel, old_level)
            bus = EventBus()
            EventLogger(bus)
            events = []
            for event_type in EventType:
                bus.subscribe(event_type, events.append)
            memory_repository = SQLiteMemoryRepository(db)
            memory = MemoryPipeline(memory_repository)
            chat = ChatController(
                provider,
                conversation_repository=repo,
                conversation_id=conversation.id,
                memory_pipeline=memory,
                memory_repository=memory_repository,
            )
            controller = ActionClarificationController(ActionClarificationService())
            window = ChatWindow()
            self.addCleanup(self.destroy_window, controller, window)
            executed = []
            panel = ActionClarificationPanel(controller, executed.append, window)
            window.layout().insertWidget(2, panel)
            controller.on_pending = panel.refresh_requested.emit
            notifications = SQLiteNotificationRepository(db)
            now = datetime.now(UTC)
            notification_coordinator = IntegrationNotificationCoordinator(
                event_bus=bus,
                validator=ExternalEventValidator(),
                repository=SQLiteExternalEventRepository(db),
                notification_policy=NotificationPolicy(BehaviorConfig()),
                renderer=ExternalNotificationRenderer(),
                activity_provider=lambda: ActivitySnapshot(
                    ActivityState.ACTIVE, 0, now, "test"
                ),
                schedule_on_app_thread=lambda callback: callback(),
                now_provider=lambda: now,
                inbox_repository=notifications,
                preference_provider=lambda: ExternalIntegrationsConfig(
                    voice_notifications_enabled=False
                ),
            )
            ProactiveDeliveryController(
                bus,
                ProactiveDeliveryService(),
                QtProactiveDeliverySurface(
                    window, SimpleNamespace(isVisible=lambda: False)
                ),
            )
            bridge = Mock()
            bridge.parse_user_text.return_value = None
            context = Mock(current_directory=None)
            context.resolve.return_value = None

            async def respond(value):
                async for _ in chat.stream_user_message(value):
                    pass

            scope = dict(
                action_clarification=controller,
                ClarificationOutcome=ClarificationOutcome,
                uuid4=uuid4,
                refresh_assistant_action_aliases=lambda: None,
                assistant_action_bridge=bridge,
                IntentProposalSource=IntentProposalSource,
                ephemeral_action_context=context,
                ActionRequest=ActionRequest,
                EphemeralSelectionReference=EphemeralSelectionReference,
                EphemeralDirectoryReference=EphemeralDirectoryReference,
                EphemeralReferenceError=EphemeralReferenceError,
                parse_directory_navigation_proposal=parse_directory_navigation_proposal,
                re=re,
                clarification_panel=panel,
                chat_window=window,
                assistant_tool_gateway=SimpleNamespace(enabled=False),
                intent_arbiter=Mock(),
                start_chat_response=lambda value: asyncio.run(respond(value)),
                start_action_thread=executed.append,
            )
            scope["looks_like_private_path"] = looks_like_private_path
            exec(
                compile(
                    ast.Module(body=[body], type_ignores=[]), str(main_path), "exec"
                ),
                scope,
            )
            window.message_submitted.connect(scope["submit_chat_message"])
            for command in ("please open file", "please open folder"):
                window.message_submitted.emit(command)
                self.assertIsNotNone(controller.leases.pending)
                original = controller.leases.pending.identity
                for text in PATH_REPLIES:
                    with self.subTest(command=command, reply=text):
                        window.message_submitted.emit(text)
                        self.assertEqual(controller.leases.pending.identity, original)
            panel._answer.setText("/home/Alice/PANEL_SECRET123.mp3")
            panel._resolve(cancel=True)
            self.assertEqual(executed, [])
            self.assertEqual(window._history_view.toPlainText(), "")
            self.assertEqual(chat.messages, ())
            self.assertEqual(
                asyncio.run(memory_repository.get_recent_memories(100)), ()
            )
            self.assertEqual(notifications.list_recent(), ())
            self.assertEqual(provider.stream_messages, ())
            # Positive control: this SAME wiring really reaches provider/storage.
            window.message_submitted.emit("please open file")
            ordinary_owner = controller.leases.pending.identity
            window.message_submitted.emit("I prefer coffee with oat milk.")
            self.assertEqual(controller.leases.pending.identity, ordinary_owner)
            self.assertIn("I prefer coffee", repr(provider.stream_messages))
            self.assertTrue(asyncio.run(memory_repository.get_recent_memories(100)))
            exports = asyncio.run(chat.get_export_messages())
            exported = render_chat_transcript(exports, assistant_name="Akiha")
            export_path = Path(temp) / "export.txt"
            write_chat_transcript(export_path, exported)
            prompts = asyncio.run(chat.build_provider_messages("ordinary follow-up"))
            asyncio.run(chat.start_new_conversation())
            surfaces = [
                window._history_view.toPlainText(),
                repr(prompts),
                repr(asyncio.run(memory_repository.get_recent_memories(100))),
                export_path.read_text(encoding="utf-8"),
            ]
            # Positive control goes through the real ingress, delivery, inbox and
            # EventLogger attached to the same surface being checked for leaks.
            window.show()
            notification_coordinator.submit(
                ExternalEvent(
                    service=ExternalService.GMAIL,
                    external_id="privacy-positive-control",
                    kind=ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
                    occurred_at=now,
                    sender_display="Synthetic Recruiter",
                    subject="PUBLIC_NOTIFICATION_CONTROL",
                    context_label="Inbox",
                    classification=ExternalClassification.INTERVIEW,
                    priority=ExternalEventPriority.IMPORTANT,
                )
            )
            self.assertTrue(notifications.list_recent())
            self.assertIn("Synthetic Recruiter", window._history_view.toPlainText())
            self.assertTrue(
                any("proactive.suggestion_delivered" in entry for entry in logged)
            )
            surfaces.extend(
                (window._history_view.toPlainText(), repr(provider.stream_messages))
            )
            surfaces.append(repr(events))
            surfaces.extend(logged)
            with closing(sqlite3.connect(db)) as connection:
                for (table,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ):
                    surfaces.append(
                        repr(
                            connection.execute(
                                'SELECT * FROM "' + table + '"'
                            ).fetchall()
                        )
                    )
                summaries = connection.execute(
                    "SELECT summary FROM conversations"
                ).fetchall()
                self.assertIn("coffee", repr(summaries).casefold())
            self.assertNotIn("SECRET123", "\n".join(surfaces))

    @staticmethod
    def destroy_window(controller, window):
        controller.on_pending = None
        controller.invalidate()
        window.message_submitted.disconnect()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class CorrectionProviderPathTest(unittest.TestCase):
    def test_attack_paths_rejected_before_any_local_resolution(self):
        authority = SimpleNamespace(accepts_callback=lambda *_: True)
        attacks = tuple(
            path
            for path in PATH_REPLIES
            if path
            not in {
                "Downloads/Private/SECRET123.mp3",
                "Downloads/Private Folder/SECRET123.mp3",
                "My Downloads/Private Folder/SECRET123.mp3",
            }
        ) + (
            ".Downloads",
            "Downloads;folder",
            "Downloads#folder",
            "Downloads folder",
            "Downloads directory",
            "Downloads/../",
            "../Downloads",
            "Downloads\\..",
            "Downloads/./",
            "Downloads//",
            "Downloads/..\\",
            "Downloads/Video\\song.mp3",
            "Downloads. ",
            "Downloads/%2e%2e/song.mp3",
        )
        for lane in ("gemini.live", "ollama.native"):
            gateway = ProviderActionProposalGateway(
                build_default_provider_action_catalog(), authority
            )
            gateway.set_directory_aliases({"downloads": "C:/Approved/Downloads"})
            gateway._resolve_local_arguments = Mock(
                side_effect=AssertionError("unsafe path reached resolution")
            )
            for index, path in enumerate(attacks):
                for action, field, extra in (
                    ("files.open", "path", {}),
                    ("files.open_directory", "path", {}),
                    ("files.search", "root", {"query": "song"}),
                    ("directories.search", "root", {"query": "folder"}),
                ):
                    with self.subTest(lane=lane, path=path, action=action):
                        conversion = gateway.convert(
                            ActionProposal(
                                "session-1",
                                "turn-1",
                                f"proposal-{index}-{action.replace('.', '-')}",
                                lane,
                                action,
                                {field: path, **extra},
                            )
                        )
                        self.assertFalse(conversion.decision.accepted)
                        self.assertIsNone(conversion.request)
            gateway._resolve_local_arguments.assert_not_called()

    def test_safe_descendants_and_alias_conflicts_are_preserved(self):
        authority = SimpleNamespace(accepts_callback=lambda *_: True)
        gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(), authority
        )
        gateway.set_directory_aliases({"Downloads": "C:/Approved/Downloads"})
        for index, path in enumerate(("Downloads/Video", "Downloads\\Video")):
            converted = gateway.convert(
                ActionProposal(
                    "session-1",
                    "turn-1",
                    f"safe-{index}",
                    "gemini.live",
                    "files.open_directory",
                    {"path": path},
                )
            )
            self.assertTrue(converted.decision.accepted)
            self.assertEqual(
                Path(converted.request.parameters["path"]),
                Path("C:/Approved/Downloads/Video"),
            )
        for aliases in (
            {"Music": "C:/One", "music": "D:/Two"},
            {"music": "D:/Two", "Music": "C:/One"},
            {"My-Music": "C:/One", "My Music": "D:/Two"},
            {"Downloads": "C:/One", " downloads ": "C:/One"},
        ):
            with self.assertRaises(ValueError):
                gateway.set_directory_aliases(aliases)

    def test_alias_only_trims_spaces_and_casefolds(self):
        gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(),
            SimpleNamespace(accepts_callback=lambda *_: True),
        )
        gateway.set_directory_aliases({"My Downloads": "C:/Approved/Downloads"})
        for index, alias in enumerate(
            ("My Downloads", " my downloads ", "MY DOWNLOADS")
        ):
            converted = gateway.convert(
                ActionProposal(
                    "session",
                    "turn",
                    f"alias-{index}",
                    "gemini.live",
                    "files.open_directory",
                    {"path": alias},
                )
            )
            self.assertTrue(converted.decision.accepted)
        for index, alias in enumerate(
            ("My  Downloads", "My Downloads folder", "My-Downloads", "\tMy Downloads")
        ):
            converted = gateway.convert(
                ActionProposal(
                    "session",
                    "turn",
                    f"invalid-{index}",
                    "gemini.live",
                    "files.open_directory",
                    {"path": alias},
                )
            )
            self.assertFalse(converted.decision.accepted)


class _ManualWorkerSignals(QObject):
    finished = Signal()


class _ManualStartWorker:
    """Exercise real worker methods without simulating native thread termination."""

    def __init__(self, worker):
        self.worker = worker
        self.start = Mock()
        self.signals = _ManualWorkerSignals()
        self.finished = self.signals.finished

    def __getattr__(self, name):
        return getattr(self.worker, name)


class _SessionWorker(QObject):
    """Session callback double; audio-drop checks use the real worker separately."""

    connected = Signal()
    transcript_revised_signal = Signal(object)
    assistant_text_revised_signal = Signal(object)
    audio_received_signal = Signal(object)
    action_confirmation_requested_signal = Signal(object)
    local_action_result_signal = Signal(object, object)
    response_interrupted_signal = Signal(str)
    turn_completed_signal = Signal(str)
    failed_signal = Signal(str, str)
    session_state_changed_signal = Signal(object)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.cloud_audio_paused = False
        self.start = Mock()
        self.request_stop = Mock()

    def pause_for_clarification(self, turn_id):
        self.cloud_audio_paused = True

    def is_noncanonical_turn(self, turn_id):
        return self.cloud_audio_paused


class CorrectionHostedSuspensionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def build_runtime(self, *, session_double=False):
        fixture = flows.Phase13BProposalFlowTest()
        fixture.setUp()
        if session_double:
            worker = _SessionWorker()
            turn = SimpleNamespace(session_id="session", turn_id="turn")
        else:
            worker, turn, _, _, _ = fixture.hosted()
            worker = _ManualStartWorker(worker)
        voice = Mock(state=VoiceState.IDLE, operation="none")
        voice.config = SimpleNamespace(enabled=True, push_to_talk_enabled=True)
        coordinator = Mock()
        coordinator.snapshot = SimpleNamespace(
            lifecycle=SessionLifecycle.IDLE, session_id=turn.session_id
        )
        coordinator.accepts_callback.return_value = True
        runtime = HostedConversationRuntime(
            event_bus=Mock(),
            coordinator=coordinator,
            voice_controller=voice,
            audio_bridge=Mock(),
            playback=Mock(),
            transcripts=Mock(commit_completed_turn=AsyncMock(return_value=None)),
            thread_factory=Mock(),
            on_commit=Mock(),
            clarification_controller=fixture.controller,
        )
        runtime._thread = worker
        runtime._turn_id = turn.turn_id
        runtime._active = True
        runtime._connect_thread(worker)
        self.addCleanup(self.release_runtime, fixture, runtime, worker)
        # Run the real composition-root assignment, not a parallel test-only wire.
        main = Path(__file__).resolve().parents[3] / "project_akiha/app/main.py"
        statement = next(
            n
            for n in ast.walk(ast.parse(main.read_text(encoding="utf-8")))
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "before_pending"
                for t in n.targets
            )
        )
        exec(
            compile(ast.Module(body=[statement], type_ignores=[]), str(main), "exec"),
            {
                "action_clarification": fixture.controller,
                "hosted_conversation_runtime": runtime,
            },
        )
        return fixture, runtime, worker, turn

    @staticmethod
    def release_runtime(fixture, runtime, worker):
        fixture.controller.before_pending = None
        fixture.controller.on_pending = None
        runtime._thread = None
        for name in (
            "connected",
            "transcript_revised_signal",
            "assistant_text_revised_signal",
            "audio_received_signal",
            "action_confirmation_requested_signal",
            "local_action_result_signal",
            "response_interrupted_signal",
            "turn_completed_signal",
            "failed_signal",
            "session_state_changed_signal",
            "finished",
        ):
            getattr(worker, name).disconnect()
        worker.deleteLater()
        if isinstance(worker, _ManualStartWorker):
            worker.signals.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_local_question_suspends_before_presentation_and_drops_queued_audio(self):
        fixture, runtime, worker, turn = self.build_runtime()
        observations = []
        fixture.controller.on_pending = lambda: observations.append(
            worker.cloud_audio_paused
        )
        fixture.controller.prepare(
            ActionRequest("local", "applications.launch", "chat", {})
        )
        self.assertEqual(observations, [True])
        self.assertTrue(fixture.leases.pending.spec.cloud_origin)
        self.assertFalse(worker.submit_audio(_frame(turn_id=turn.turn_id)))
        forwarded = []

        class AudioSink:
            async def accept_audio(self, frame):
                forwarded.append(frame)

        asyncio.run(
            worker._accept_unpaused_audio(AudioSink(), _frame(turn_id=turn.turn_id))
        )
        self.assertEqual(forwarded, [])
        runtime._handle_audio(_frame(turn_id=turn.turn_id))
        runtime._playback.submit.assert_not_called()
        runtime._handle_transcript(Mock())
        runtime._transcripts.transcript_revised.assert_not_called()
        self.assertEqual(
            fixture.controller.route_answer("spotify").outcome,
            ClarificationOutcome.INVALID,
        )
        self.assertFalse(runtime.start())

    def test_resolution_cancel_expiry_supersession_require_explicit_fresh_session(self):
        for transition in ("resolve", "cancel", "expire", "supersede"):
            with self.subTest(transition=transition):
                fixture, runtime, old, turn = self.build_runtime(session_double=True)
                clock = FakeClock()
                fixture.leases.clock = clock
                fixture.controller.prepare(
                    ActionRequest("local", "applications.launch", "chat", {})
                )
                pending = fixture.leases.pending
                runtime._handle_turn_completed(turn.turn_id)
                self.assertFalse(runtime.active)
                runtime._transcripts.commit_completed_turn.assert_not_called()
                runtime._transcripts.cancel_turn.assert_called_with(turn.turn_id)
                runtime._voice_controller.notify_error.assert_not_called()
                old.request_stop.assert_called_once()
                self.assertEqual(
                    runtime._event_bus.publish.call_args.args[1]["reason"],
                    "clarification_pending",
                )
                runtime._thread_factory.assert_not_called()
                if transition in {"resolve", "cancel"}:
                    fixture.controller.resolve(
                        ClarificationAnswer(
                            pending.identity,
                            ClarificationAnswerSource.LOCAL_UI,
                            "spotify",
                            cancel=transition == "cancel",
                        )
                    )
                elif transition == "expire":
                    clock.seconds = pending.identity.deadline
                    self.assertIsNone(fixture.leases.pending)
                else:
                    fixture.controller.prepare(
                        ActionRequest(
                            "new-explicit",
                            "applications.launch",
                            "chat",
                            {"application_id": "chrome"},
                        )
                    )
                self.assertTrue(old.cloud_audio_paused)
                runtime._thread_factory.assert_not_called()
                fresh = _SessionWorker()
                self.addCleanup(self.release_runtime, fixture, runtime, fresh)
                runtime._thread_factory.return_value = fresh
                self.assertTrue(runtime.start())
                fresh.start.assert_called_once()
                fixture.controller.prepare(
                    ActionRequest("new-question", "files.open", "chat", {})
                )
                newer = fixture.leases.pending
                old.finished.emit()
                old.failed_signal.emit("stale", "old session failure")
                old.turn_completed_signal.emit(turn.turn_id)
                self.assertIs(runtime._thread, fresh)
                self.assertTrue(runtime.active)
                self.assertEqual(fixture.leases.pending, newer)
                self.assertTrue(fresh.cloud_audio_paused)
                runtime._voice_controller.notify_error.assert_not_called()
                fresh.request_stop.assert_not_called()

    def test_queued_playback_completion_cannot_start_another_turn_while_paused(self):
        fixture, runtime, worker, _ = self.build_runtime()
        fixture.controller.prepare(
            ActionRequest("local", "applications.launch", "chat", {})
        )
        runtime._handle_playback_completed()
        runtime._coordinator.begin_turn.assert_not_called()
        self.assertFalse(runtime.active)
        self.assertTrue(worker.cloud_audio_paused)
