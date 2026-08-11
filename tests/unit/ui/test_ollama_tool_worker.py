"""Tests for the Ollama native-tool Qt worker."""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from project_akiha.core.actions import (
    LAUNCH_APPLICATION_ACTION,
    ActionRequest,
    ActionResult,
    ActionStatus,
    PermissionDecision,
    build_default_provider_action_catalog,
)
from project_akiha.core.voice_session import ActionProposal
from project_akiha.providers.ai import (
    ChatMessage,
    OllamaNativeToolTurn,
    OllamaProviderError,
)
from project_akiha.services.intent_arbitration import IntentArbiter
from project_akiha.ui.ollama_tool_worker import OllamaNativeToolThread


@dataclass(frozen=True)
class _Message:
    content: str


@dataclass(frozen=True)
class _Commit:
    assistant_message: _Message


class OllamaNativeToolThreadTest(unittest.TestCase):
    """Verify the worker preserves V7 conversion and dispatch boundaries."""

    def test_native_proposal_is_dispatched_and_committed(self) -> None:
        provider = _NativeProvider()
        controller = _ChatController()
        action_service = _ActionService()
        worker = OllamaNativeToolThread(
            provider=provider,  # type: ignore[arg-type]
            chat_controller=controller,  # type: ignore[arg-type]
            message="Please open Spotify.",
            catalog=build_default_provider_action_catalog(),
            action_service=action_service,
            intent_arbiter=IntentArbiter(),
        )

        asyncio.run(worker._run_turn())

        self.assertEqual(len(action_service.requests), 1)
        request, confirmed = action_service.requests[0]
        self.assertEqual(request.action_id, LAUNCH_APPLICATION_ACTION)
        self.assertEqual(request.source, "provider.ollama.native")
        self.assertFalse(confirmed)
        self.assertEqual(len(provider.results), 1)
        self.assertEqual(provider.results[0].status, "success")
        self.assertEqual(
            controller.commits,
            [("Please open Spotify.", "The local action completed.")],
        )

    def test_confirmation_is_resolved_only_through_local_signal(self) -> None:
        provider = _NativeProvider()
        controller = _ChatController()
        action_service = _ActionService(require_confirmation=True)
        worker = OllamaNativeToolThread(
            provider=provider,  # type: ignore[arg-type]
            chat_controller=controller,  # type: ignore[arg-type]
            message="Please open Spotify.",
            catalog=build_default_provider_action_catalog(),
            action_service=action_service,
            intent_arbiter=IntentArbiter(),
        )
        worker.confirmation_requested.connect(
            lambda confirmation: worker.resolve_confirmation(
                confirmation,
                approved=True,
            )
        )

        asyncio.run(worker._run_turn())

        self.assertEqual(
            tuple(confirmed for _request, confirmed in action_service.requests),
            (False, True),
        )
        self.assertEqual(provider.results[0].status, "success")

    def test_model_without_tools_requests_fallback_without_provider_chat(self) -> None:
        provider = _NativeProvider(supports_tools=False)
        controller = _ChatController()
        worker = OllamaNativeToolThread(
            provider=provider,  # type: ignore[arg-type]
            chat_controller=controller,  # type: ignore[arg-type]
            message="Please open Spotify.",
            catalog=build_default_provider_action_catalog(),
            action_service=_ActionService(),
            intent_arbiter=IntentArbiter(),
        )
        unavailable: list[bool] = []
        worker.native_tools_unavailable.connect(lambda: unavailable.append(True))

        asyncio.run(worker._run_turn())

        self.assertEqual(unavailable, [True])
        self.assertFalse(provider.requested)
        self.assertEqual(controller.commits, [])

    def test_capability_check_failure_uses_safe_fallback_handoff(self) -> None:
        provider = _NativeProvider(capability_error=True)
        controller = _ChatController()
        worker = OllamaNativeToolThread(
            provider=provider,  # type: ignore[arg-type]
            chat_controller=controller,  # type: ignore[arg-type]
            message="Please open Spotify.",
            catalog=build_default_provider_action_catalog(),
            action_service=_ActionService(),
            intent_arbiter=IntentArbiter(),
        )
        unavailable: list[bool] = []
        failures: list[str] = []
        worker.native_tools_unavailable.connect(lambda: unavailable.append(True))
        worker.failed.connect(failures.append)

        asyncio.run(worker._run_turn())

        self.assertEqual(unavailable, [True])
        self.assertEqual(failures, [])
        self.assertFalse(provider.requested)


class _NativeProvider:
    def __init__(
        self,
        *,
        supports_tools: bool = True,
        capability_error: bool = False,
    ) -> None:
        self._supports_tools = supports_tools
        self._capability_error = capability_error
        self.requested = False
        self.results = []

    async def supports_native_tools(self) -> bool:
        if self._capability_error:
            raise OllamaProviderError("model details unavailable")
        return self._supports_tools

    async def request_native_tool_turn(
        self,
        _messages,
        _tools,
        *,
        session_id: str,
        turn_id: str,
    ) -> OllamaNativeToolTurn:
        self.requested = True
        proposal = ActionProposal(
            session_id=session_id,
            turn_id=turn_id,
            proposal_id="ollama-proposal",
            source="ollama.native",
            action_name=LAUNCH_APPLICATION_ACTION,
            arguments={"application_id": "spotify"},
        )
        return OllamaNativeToolTurn(
            session_id=session_id,
            turn_id=turn_id,
            proposals=(proposal,),
            _request_messages_json="[]",
            _assistant_message_json="{}",
            _tool_names=("akiha_applications_launch",),
        )

    async def complete_native_tool_turn(self, _turn, results) -> str:
        self.results = list(results)
        return "The local action completed."


class _ChatController:
    def __init__(self) -> None:
        self.commits: list[tuple[str, str | None]] = []

    async def build_provider_messages(self, message: str):
        return (ChatMessage(role="user", content=message),)

    async def commit_canonical_live_turn(
        self,
        user_content: str,
        assistant_content: str | None,
    ) -> _Commit:
        self.commits.append((user_content, assistant_content))
        return _Commit(_Message(assistant_content or ""))


class _ActionService:
    def __init__(self, *, require_confirmation: bool = False) -> None:
        self._require_confirmation = require_confirmation
        self.requests: list[tuple[ActionRequest, bool]] = []

    async def evaluate_request(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token=None,
    ) -> ActionResult:
        del cancellation_token
        self.requests.append((request, confirmed))
        status = (
            ActionStatus.CONFIRMATION_REQUIRED
            if self._require_confirmation and not confirmed
            else ActionStatus.SUCCESS
        )
        return ActionResult(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            status=status,
            summary="Local action result.",
            permission_decision=(
                PermissionDecision.CONFIRMATION_REQUIRED
                if status is ActionStatus.CONFIRMATION_REQUIRED
                else PermissionDecision.GRANTED
            ),
        )


if __name__ == "__main__":
    unittest.main()
