"""Tests for final speech crossing Akiha's real typed-action boundary."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    LAUNCH_APPLICATION_ACTION,
    ActionExecutionResult,
    ActionFailureCategory,
    ActionPermissionPolicy,
    ActionRequestValidator,
    ActionStatus,
    PermissionDecision,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.database import SQLiteActionRepository
from project_akiha.providers.ai import ChatMessage
from project_akiha.services.assistant_action_bridge import AssistantActionBridge
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolKind,
    AssistantToolProposalError,
    LLMAssistantToolGateway,
)
from spikes.voice_pipeline.action_gateway_probe import TypedActionGatewayProbe
from spikes.voice_pipeline.pipeline_spike import TranscriptRevision


class TypedActionGatewayProbeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        root = Path(self._temporary_directory.name)
        path_policy = ProtectedPathPolicy()
        self.repository = SQLiteActionRepository(root / "akiha.sqlite3")
        self.permissions = AssistantPermissionService(self.repository, path_policy)
        self.executor = _RecordingLaunchExecutor()
        service = AssistantActionService(
            ActionRequestValidator(build_default_action_registry(), path_policy),
            ActionPermissionPolicy(path_policy),
            self.repository,
            self.repository,
            executors=(self.executor,),
        )
        self.action_bridge = AssistantActionBridge(service)

    async def test_final_proposal_uses_real_permission_executor_and_audit_path(
        self,
    ) -> None:
        provider = _FakeProvider(
            '{"action":"launch_application","application_id":"spotify"}'
        )
        probe = self._probe(provider)
        await self.permissions.grant_application("spotify")

        probe.observe_partial(1, TranscriptRevision("Open Spot", 1))
        self.assertEqual(provider.messages, ())
        self.assertEqual(self.executor.targets, [])
        self.assertEqual(await self.repository.get_recent_action_audits(10), ())

        outcome = await probe.commit_final(
            1,
            TranscriptRevision("Akiha, open Spotify.", 2, is_final=True),
        )
        audits = await self.repository.get_recent_action_audits(10)

        self.assertEqual(outcome.proposal.kind, AssistantToolKind.LAUNCH_APPLICATION)
        self.assertIsNotNone(outcome.dispatch)
        assert outcome.dispatch is not None
        self.assertEqual(outcome.dispatch.request.action_id, LAUNCH_APPLICATION_ACTION)
        self.assertEqual(
            outcome.dispatch.request.parameters["application_id"], "spotify"
        )
        self.assertEqual(outcome.dispatch.result.status, ActionStatus.SUCCESS)
        self.assertEqual(self.executor.targets, ["spotify"])
        self.assertTrue(
            all(isinstance(message, ChatMessage) for message in provider.messages)
        )
        self.assertNotIn("C:\\", provider.messages[0].content)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].source, "voice_llm_proposal")
        self.assertEqual(audits[0].permission_decision, PermissionDecision.GRANTED)

    async def test_valid_proposal_without_permission_is_denied_and_audited(
        self,
    ) -> None:
        provider = _FakeProvider(
            '{"action":"launch_application","application_id":"discord"}'
        )

        outcome = await self._probe(provider).commit_final(
            2,
            TranscriptRevision("Open Discord", 1, is_final=True),
        )
        audits = await self.repository.get_recent_action_audits(10)

        assert outcome.dispatch is not None
        self.assertEqual(outcome.dispatch.result.status, ActionStatus.DENIED)
        self.assertEqual(
            outcome.dispatch.result.failure_category,
            ActionFailureCategory.PERMISSION_REQUIRED,
        )
        self.assertEqual(self.executor.targets, [])
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].permission_decision, PermissionDecision.MISSING)

    async def test_invalid_provider_target_fails_before_action_service(self) -> None:
        provider = _FakeProvider(
            '{"action":"launch_application","application_id":"powershell",'
            '"command":"whoami"}'
        )

        with self.assertRaises(AssistantToolProposalError):
            await self._probe(provider).commit_final(
                3,
                TranscriptRevision("Run a system command", 1, is_final=True),
            )

        self.assertEqual(self.executor.targets, [])
        self.assertEqual(await self.repository.get_recent_action_audits(10), ())

    async def test_media_proposal_requires_trusted_local_resolution(self) -> None:
        provider = _FakeProvider(
            '{"action":"play_media","title":"Elis",'
            '"artist":"Megurine Luka","media_kind":"audio"}'
        )

        outcome = await self._probe(provider).commit_final(
            4,
            TranscriptRevision("Play Elis", 1, is_final=True),
        )

        self.assertEqual(outcome.proposal.kind, AssistantToolKind.PLAY_MEDIA)
        self.assertIsNone(outcome.dispatch)
        self.assertEqual(self.executor.targets, [])
        self.assertEqual(await self.repository.get_recent_action_audits(10), ())

    async def test_only_one_authoritative_final_can_commit_each_turn(self) -> None:
        provider = _FakeProvider('{"action":"none"}')
        probe = self._probe(provider)

        with self.assertRaisesRegex(ValueError, "authoritative final"):
            await probe.commit_final(5, TranscriptRevision("Open", 1))
        await probe.commit_final(
            5,
            TranscriptRevision("Never mind", 2, is_final=True),
        )
        with self.assertRaisesRegex(RuntimeError, "already committed"):
            await probe.commit_final(
                5,
                TranscriptRevision("Open Chrome", 3, is_final=True),
            )

        self.assertEqual(provider.request_count, 1)
        self.assertEqual(await self.repository.get_recent_action_audits(10), ())

    def _probe(self, provider: _FakeProvider) -> TypedActionGatewayProbe:
        gateway = LLMAssistantToolGateway(provider, enabled=True)
        return TypedActionGatewayProbe(gateway, self.action_bridge)


class _FakeProvider:
    def __init__(self, response: str) -> None:
        self._response = response
        self.messages: tuple[ChatMessage, ...] = ()
        self.request_count = 0

    async def generate_response(self, messages) -> str:
        self.request_count += 1
        self.messages = tuple(messages)
        return self._response


class _RecordingLaunchExecutor:
    executor_id = "launch_allowlisted_application"
    action_id = LAUNCH_APPLICATION_ACTION

    def __init__(self) -> None:
        self.targets: list[str] = []

    async def execute(self, action, *, cancellation_token) -> ActionExecutionResult:
        if cancellation_token.is_cancelled:
            return ActionExecutionResult(
                status=ActionStatus.CANCELLED,
                summary="Application launch was cancelled.",
            )
        self.targets.append(action.normalized_target)
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary="The allowlisted application was started.",
        )


if __name__ == "__main__":
    unittest.main()
