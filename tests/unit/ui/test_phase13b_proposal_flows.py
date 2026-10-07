"""Shared ownership, cloud pause, native batches and noncanonical tool turns."""

from __future__ import annotations

import asyncio
import os
import unittest
from dataclasses import replace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.app.hosted_conversation_runtime import HostedConversationRuntime
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.actions import (
    ActionRequest,
    build_default_provider_action_catalog,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.core.voice_session import (
    ActionProposal,
    VoiceInputMode,
    VoiceProcessingMode,
)
from project_akiha.providers.ai.ollama_provider import OllamaProvider
from project_akiha.providers.live.google_transport import _translate_sdk_message
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.intent_arbitration import IntentArbiter
from project_akiha.services.provider_action_dispatcher import ProviderActionDispatcher
from project_akiha.services.provider_action_proposal_gateway import (
    ProviderActionProposalGateway,
)
from project_akiha.ui.action_clarification_panel import ActionClarificationPanel
from project_akiha.ui.chat_window import ChatWindow
from project_akiha.ui.hosted_live_session_worker import HostedLiveSessionThread
from project_akiha.ui.ollama_tool_worker import OllamaNativeToolThread
from tests.unit.ui.test_hosted_live_session_worker import _config, _frame
from tests.unit.ui.test_ollama_tool_worker import (
    _ActionService,
    _ChatController,
    _NativeProvider,
)


class _MissingOrCompoundProvider(_NativeProvider):
    def __init__(self, *, compound=False):
        super().__init__()
        self.compound = compound

    async def request_native_tool_turn(self, *args, **kwargs):
        turn = await super().request_native_tool_turn(*args, **kwargs)
        first = replace(turn.proposals[0], arguments={})
        proposals = (first,)
        if self.compound:
            proposals = (turn.proposals[0], replace(first, proposal_id="proposal-two"))
        return replace(
            turn, proposals=proposals, _tool_names=turn._tool_names * len(proposals)
        )


class Phase13BProposalFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.leases = ActionClarificationService()
        self.controller = ActionClarificationController(self.leases)
        self.catalog = build_default_provider_action_catalog()

    def test_vague_spotify_music_renders_local_song_question_without_execution(self):
        executed = Mock()
        panel = ActionClarificationPanel(self.controller, executed)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.close)
        request = self.controller.incomplete_command(
            "Play Music on Spotify", "spotify-panel"
        )
        self.assertFalse(self.controller.prepare(request))
        panel.refresh()
        self.assertIn("Loading Spotify recently played", panel._label.text())
        self.assertTrue(panel._answer.isHidden())
        panel._spotify_mode.setCurrentIndex(1)
        self.assertIn(
            "Which song would you like to play on Spotify", panel._label.text()
        )
        self.assertFalse(panel._answer.isHidden())
        self.assertTrue(panel._choices.isHidden())
        executed.assert_not_called()
        panel._answer.setText("Blinding Lights")
        panel._submit.click()
        self.assertEqual(executed.call_count, 1)
        self.assertEqual(
            executed.call_args.args[0].parameters["track_query"], "Blinding Lights"
        )
        self.assertIsNone(self.leases.pending)

    def hosted(self):
        coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "hosted-session-1"
        )
        coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
        coordinator.activate()
        turn = coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        service = _ActionService()
        gateway = ProviderActionProposalGateway(self.catalog, coordinator)
        dispatcher = ProviderActionDispatcher(
            service,
            coordinator,
            IntentArbiter(),
            clarification_controller=self.controller,
        )
        worker = HostedLiveSessionThread(
            adapter_factory=lambda: None,
            coordinator=coordinator,
            config_provider=_config,
            proposal_gateway=gateway,
            action_dispatcher=dispatcher,
        )
        returned = []

        class Controller:
            async def accept_action_result(self, result):
                returned.append(result)

            async def accept_audio(self, frame):
                raise AssertionError(
                    "private cloud clarification forwarded microphone audio"
                )

        worker._controller = Controller()
        return worker, turn, service, gateway, returned

    def test_gemini_pauses_audio_before_local_question_and_never_resumes_automatically(
        self,
    ):
        worker, turn, service, _, returned = self.hosted()
        paused_at_question = []
        self.controller.on_pending = lambda: paused_at_question.append(
            worker._cloud_audio_paused.is_set()
        )
        proposal = ActionProposal(
            turn.session_id,
            turn.turn_id,
            "proposal-1",
            "gemini.live",
            "applications.launch",
            {},
        )
        asyncio.run(worker._dispatch_action_proposal(proposal))
        self.assertEqual(paused_at_question, [True])
        self.assertEqual(service.requests, [])
        self.assertEqual(returned[0].status, "clarification_required")
        self.assertFalse(worker.submit_audio(_frame(turn_id=turn.turn_id)))
        asyncio.run(
            worker._accept_unpaused_audio(
                worker._controller, _frame(turn_id=turn.turn_id)
            )
        )
        self.assertTrue(worker.is_noncanonical_turn(turn.turn_id))
        pending = self.leases.pending
        for source in (
            ClarificationAnswerSource.PROVIDER,
            ClarificationAnswerSource.LOCAL_FINAL_TRANSCRIPT,
            ClarificationAnswerSource.LOCAL_TEXT,
        ):
            result = self.controller.resolve(
                ClarificationAnswer(pending.identity, source, "spotify")
            )
            self.assertEqual(result.outcome, ClarificationOutcome.INVALID)
        self.assertEqual(
            self.controller.resolve(
                ClarificationAnswer(
                    pending.identity, ClarificationAnswerSource.LOCAL_UI, "spotify"
                )
            ).outcome,
            ClarificationOutcome.RESOLVED,
        )
        self.assertFalse(worker.submit_audio(_frame(turn_id=turn.turn_id)))

    def test_cloud_clarification_turn_never_commits_or_processes_memory(self):
        worker, turn, _, _, _ = self.hosted()
        worker.pause_for_clarification(turn.turn_id)
        transcripts = Mock()
        callback = Mock()
        runtime = HostedConversationRuntime(
            event_bus=Mock(),
            coordinator=Mock(),
            voice_controller=Mock(),
            audio_bridge=Mock(),
            playback=Mock(),
            transcripts=transcripts,
            thread_factory=Mock(),
            on_commit=callback,
        )
        runtime._thread = worker
        runtime._owns_turn = lambda _: True
        runtime._release_turn = Mock()
        runtime._set_inactive = Mock()
        runtime._handle_turn_completed(turn.turn_id)
        transcripts.cancel_turn.assert_called_once_with(turn.turn_id)
        transcripts.commit_completed_turn.assert_not_called()
        transcripts.turn_completed.assert_not_called()
        callback.assert_not_called()

    def test_ollama_clarification_has_no_provider_completion_or_commit(
        self,
    ):
        provider = _MissingOrCompoundProvider()
        chat = _ChatController()
        service = _ActionService()
        worker = OllamaNativeToolThread(
            provider=provider,
            chat_controller=chat,
            message="open an app",
            catalog=self.catalog,
            action_service=service,
            intent_arbiter=IntentArbiter(),
            clarification_controller=self.controller,
        )
        asyncio.run(worker._run_turn())
        self.assertEqual(service.requests, [])
        self.assertEqual(provider.results, [])
        self.assertEqual(chat.commits, [])
        self.assertIsNotNone(self.leases.pending)
        self.assertIs(worker._dispatcher.clarification_controller, self.controller)

    def test_native_compound_response_executes_no_prefix_and_commits_nothing(self):
        self.controller.prepare(ActionRequest("old-request", "files.open", "chat", {}))
        old = self.leases.pending
        provider = _MissingOrCompoundProvider(compound=True)
        chat = _ChatController()
        service = _ActionService()
        worker = OllamaNativeToolThread(
            provider=provider,
            chat_controller=chat,
            message="open apps",
            catalog=self.catalog,
            action_service=service,
            intent_arbiter=IntentArbiter(),
            clarification_controller=self.controller,
        )
        asyncio.run(worker._run_turn())
        self.assertEqual(service.requests, [])
        self.assertEqual(provider.results, [])
        self.assertEqual(chat.commits, [])
        self.assertIsNone(self.leases.pending)
        self.assertEqual(
            self.controller.resolve(
                ClarificationAnswer(
                    old.identity, ClarificationAnswerSource.LOCAL_UI, "C:/private/a.mp3"
                )
            ).outcome,
            ClarificationOutcome.STALE,
        )

    def test_gemini_compound_batch_is_rejected_without_execution(self):
        worker, turn, service, _, returned = self.hosted()
        for index in range(2):
            proposal = ActionProposal(
                turn.session_id,
                turn.turn_id,
                f"proposal-{index}",
                "gemini.live",
                "applications.launch",
                {"application_id": "spotify"},
                batch_id="batch-1",
                batch_size=2,
                batch_index=index,
            )
            asyncio.run(worker._dispatch_action_proposal(proposal))
        self.assertEqual(service.requests, [])
        self.assertEqual([result.status for result in returned], ["denied", "denied"])

    def test_absolute_paths_and_provider_open_any_rejected_before_alias_resolution(
        self,
    ):
        _, turn, _, gateway, _ = self.hosted()
        gateway.set_directory_aliases({"downloads": r"C:\Private\Downloads"})
        for index, path in enumerate(
            (
                r"C:\Private\song.mp3",
                r"\\host\share\song.mp3",
                "/private/song.mp3",
                "C:relative.mp3",
                "  C:/Private/song.mp3  ",
                "\nC:/Private/song.mp3",
            )
        ):
            result = gateway.convert(
                ActionProposal(
                    turn.session_id,
                    turn.turn_id,
                    f"proposal-{index}",
                    "gemini.live",
                    "files.open",
                    {"path": path},
                )
            )
            self.assertFalse(result.decision.accepted)
            self.assertIsNone(result.request)
        result = gateway.convert(
            ActionProposal(
                turn.session_id,
                turn.turn_id,
                "proposal-any",
                "gemini.live",
                "files.search",
                {"root": "downloads", "query": "song", "result_mode": "open_any"},
            )
        )
        self.assertFalse(result.decision.accepted)
        with self.assertRaises(ValueError):
            gateway.set_directory_aliases({"Music": "C:/one", "music": "D:/two"})

    def test_typed_chat_and_modular_final_voice_resolve_same_lease_without_history(
        self,
    ):
        for local_voice in (False, True):
            request = self.controller.incomplete_command(
                "please open an app", f"request-{local_voice}"
            )
            self.assertFalse(self.controller.prepare(request))
            result = self.controller.route_answer("spotify", local_voice=local_voice)
            self.assertEqual(result.outcome, ClarificationOutcome.RESOLVED)
            self.assertEqual(result.request.action_id, "applications.launch")
            self.assertEqual(result.request.parameters, {"application_id": "spotify"})

    def test_panel_private_question_answer_and_choice_never_enter_chat_history(self):
        window = ChatWindow()
        resolved = []
        panel = ActionClarificationPanel(self.controller, resolved.append, window)
        window.layout().insertWidget(2, panel)
        self.controller.on_pending = panel.refresh_requested.emit
        request = ActionRequest("open-1", "files.open", "chat", {})
        choice = replace(request, parameters={"path": "C:/private/secret-song.mp3"})
        self.controller.choices(request, (choice,))
        panel.refresh()
        self.assertIn("secret-song", panel._choices.itemText(0))
        self.assertEqual(window._history_view.toPlainText(), "")
        panel._resolve(open_any=True)
        self.assertEqual(resolved, [choice])
        self.assertEqual(window._history_view.toPlainText(), "")
        self.assertEqual(panel._answer.text(), "")
        self.assertEqual(panel._choices.count(), 0)
        window.close()

    def test_real_native_adapters_emit_one_bounded_batch_identity(self):
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="fixture",
            transport=lambda *_: {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "akiha_applications_launch",
                                "arguments": {"application_id": "spotify"},
                            }
                        },
                        {
                            "function": {
                                "name": "akiha_applications_launch",
                                "arguments": {"application_id": "chrome"},
                            }
                        },
                    ]
                }
            },
        )
        turn = asyncio.run(
            provider.request_native_tool_turn(
                [], self.catalog.schemas, session_id="session-1", turn_id="turn-1"
            )
        )
        self.assertEqual([proposal.batch_size for proposal in turn.proposals], [2, 2])
        self.assertEqual([proposal.batch_index for proposal in turn.proposals], [0, 1])
        self.assertTrue(turn.proposals[0].batch_id)
        self.assertEqual(turn.proposals[0].batch_id, turn.proposals[1].batch_id)
        message = SimpleNamespace(
            tool_call=SimpleNamespace(
                function_calls=[
                    SimpleNamespace(
                        id="call-1", name="launch", args={"application_id": "spotify"}
                    ),
                    SimpleNamespace(
                        id="call-2", name="launch", args={"application_id": "chrome"}
                    ),
                ]
            )
        )
        events, _, _ = _translate_sdk_message(
            message,
            input_text="",
            output_text="",
            tool_action_ids={"launch": "applications.launch"},
        )
        self.assertEqual([event.batch_size for event in events], [2, 2])
        self.assertEqual([event.batch_index for event in events], [0, 1])
        self.assertEqual(events[0].batch_id, events[1].batch_id)

    def test_gemini_unknown_alias_pauses_before_question_without_local_path_resolution(
        self,
    ):
        worker, turn, service, _, _ = self.hosted()
        paused = []
        self.controller.on_pending = lambda: paused.append(
            worker._cloud_audio_paused.is_set()
        )
        proposal = ActionProposal(
            turn.session_id,
            turn.turn_id,
            "proposal-1",
            "gemini.live",
            "files.open_directory",
            {"path": "unknown hidden folder"},
        )
        asyncio.run(worker._dispatch_action_proposal(proposal))
        self.assertEqual(paused, [True])
        self.assertEqual(service.requests, [])
        self.assertTrue(self.leases.pending.spec.cloud_origin)

    def test_failed_and_truncated_searches_do_not_claim_complete_unique_discovery(self):
        from project_akiha.core.actions import (
            ActionResult,
            ActionStatus,
            FileSearchMatch,
            PermissionDecision,
        )
        from project_akiha.services.assistant_action_bridge import (
            AssistantActionDispatch,
        )
        from project_akiha.services.assistant_tool_gateway import (
            AssistantToolKind,
            AssistantToolProposal,
        )
        from project_akiha.ui.assistant_tool_worker import AssistantMediaSearchThread

        match = FileSearchMatch("song.mp3", "C:/approved/song.mp3", 1, "2026-10-06")
        for status, limited in (
            (ActionStatus.FAILED, False),
            (ActionStatus.SUCCESS, True),
        ):
            with self.subTest(status=status, limited=limited):

                class Bridge:
                    async def dispatch(
                        self,
                        request,
                        result_status=status,
                        result_limited=limited,
                        **kwargs,
                    ):
                        result = ActionResult(
                            request.correlation_id,
                            request.action_id,
                            result_status,
                            "fixture",
                            permission_decision=PermissionDecision.GRANTED,
                            metadata={"matches": (match,), "limited": result_limited},
                        )
                        return AssistantActionDispatch(request, result)

                worker = AssistantMediaSearchThread(
                    Bridge(),
                    AssistantToolProposal(AssistantToolKind.PLAY_MEDIA, title="song"),
                    ("C:/approved",),
                )
                outcome = asyncio.run(worker._search())
                self.assertEqual(outcome.matches, (match,))
                self.assertFalse(outcome.complete and not outcome.limited)
