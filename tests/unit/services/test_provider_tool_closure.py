"""Cross-layer closure checks for provider-neutral assistant tools."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.actions import (
    LAUNCH_APPLICATION_ACTION,
    ActionExecutionResult,
    ActionPermissionPolicy,
    ActionRequestValidator,
    ActionStatus,
    PermissionDecision,
    ProtectedPathPolicy,
    build_default_action_registry,
    build_default_provider_action_catalog,
)
from project_akiha.core.voice_session import (
    ActionProposal,
    ProposalState,
    VoiceInputMode,
    VoiceProcessingMode,
)
from project_akiha.database import SQLiteActionRepository
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService
from project_akiha.services.intent_arbitration import (
    IntentArbiter,
    IntentProposalSource,
)
from project_akiha.services.provider_action_dispatcher import (
    ProviderActionDispatcher,
)
from project_akiha.services.provider_action_proposal_gateway import (
    ProposalGatewayReason,
    ProviderActionProposalGateway,
)


class ProviderToolClosureTest(unittest.TestCase):
    def test_gemini_and_ollama_share_permission_audit_and_sanitization(self) -> None:
        for provider_source in ("gemini.live", "ollama.native"):
            with self.subTest(provider_source=provider_source):
                with TemporaryDirectory() as directory:
                    repository = SQLiteActionRepository(
                        Path(directory) / "akiha.sqlite3"
                    )
                    coordinator, turn, gateway, dispatcher, executor = _stack(
                        repository
                    )
                    proposal = _proposal(
                        turn.session_id,
                        turn.turn_id,
                        provider_source,
                    )
                    dispatcher.complete_local_routing(
                        turn.session_id,
                        turn.turn_id,
                    )

                    denied = asyncio.run(dispatcher.dispatch(gateway.convert(proposal)))
                    denied_audits = asyncio.run(
                        repository.get_recent_action_audits(limit=10)
                    )

                    self.assertEqual(denied.status, ActionStatus.DENIED.value)
                    self.assertEqual(executor.targets, [])
                    self.assertEqual(len(denied_audits), 1)
                    self.assertEqual(
                        denied_audits[0].permission_decision,
                        PermissionDecision.MISSING,
                    )
                    self.assertEqual(
                        denied_audits[0].source,
                        f"provider.{provider_source}",
                    )

                    coordinator.complete_turn(turn.session_id, turn.turn_id)
                    granted_turn = coordinator.begin_turn(
                        VoiceInputMode.HOSTED_LIVE_CONVERSATION
                    )
                    asyncio.run(
                        AssistantPermissionService(
                            repository,
                            ProtectedPathPolicy(),
                        ).grant_application("spotify")
                    )
                    granted_proposal = _proposal(
                        granted_turn.session_id,
                        granted_turn.turn_id,
                        provider_source,
                    )
                    dispatcher.complete_local_routing(
                        granted_turn.session_id,
                        granted_turn.turn_id,
                    )

                    granted = asyncio.run(
                        dispatcher.dispatch(gateway.convert(granted_proposal))
                    )
                    replay = gateway.convert(granted_proposal)
                    all_audits = asyncio.run(
                        repository.get_recent_action_audits(limit=10)
                    )

                self.assertEqual(granted.status, ActionStatus.SUCCESS.value)
                self.assertEqual(granted.message, "The approved action completed.")
                self.assertNotIn("spotify", repr(granted).casefold())
                self.assertNotIn("private-token", repr(granted).casefold())
                self.assertEqual(executor.targets, ["spotify"])
                self.assertFalse(replay.decision.accepted)
                self.assertEqual(
                    replay.decision.reason,
                    ProposalGatewayReason.DUPLICATE,
                )
                self.assertEqual(len(all_audits), 2)
                self.assertEqual(all_audits[0].result_status, ActionStatus.SUCCESS)

    def test_deterministic_claim_prevents_provider_execution_and_audit(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            _, turn, gateway, dispatcher, executor = _stack(repository)
            asyncio.run(
                AssistantPermissionService(
                    repository,
                    ProtectedPathPolicy(),
                ).grant_application("spotify")
            )
            conversion = gateway.convert(
                _proposal(turn.session_id, turn.turn_id, "gemini.live")
            )

            local = dispatcher.claim_local_action(
                session_id=turn.session_id,
                turn_id=turn.turn_id,
                proposal_id="local-exact-action",
                action_id=LAUNCH_APPLICATION_ACTION,
                source=IntentProposalSource.EXACT,
            )
            provider = asyncio.run(dispatcher.dispatch(conversion))
            audits = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertTrue(local.accepted)
        self.assertEqual(provider.status, ActionStatus.DENIED.value)
        self.assertEqual(executor.targets, [])
        self.assertEqual(audits, ())


class _RecordingLaunchExecutor:
    executor_id = "launch_allowlisted_application"
    action_id = LAUNCH_APPLICATION_ACTION

    def __init__(self) -> None:
        self.targets: list[str] = []

    async def execute(self, action, *, cancellation_token) -> ActionExecutionResult:
        del cancellation_token
        self.targets.append(action.normalized_target)
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary="Opened a private local target.",
            metadata={"credential": "private-token"},
        )


def _stack(repository: SQLiteActionRepository):
    coordinator = VoiceSessionCoordinator(session_id_factory=lambda: "session-v7g")
    coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
    coordinator.activate()
    turn = coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
    registry = build_default_action_registry()
    gateway = ProviderActionProposalGateway(
        build_default_provider_action_catalog(registry),
        coordinator,
    )
    executor = _RecordingLaunchExecutor()
    action_service = AssistantActionService(
        ActionRequestValidator(registry, ProtectedPathPolicy()),
        ActionPermissionPolicy(ProtectedPathPolicy()),
        repository,
        repository,
        executors=(executor,),
    )
    dispatcher = ProviderActionDispatcher(
        action_service,
        coordinator,
        IntentArbiter(),
    )
    return coordinator, turn, gateway, dispatcher, executor


def _proposal(
    session_id: str,
    turn_id: str,
    source: str,
) -> ActionProposal:
    return ActionProposal(
        session_id=session_id,
        turn_id=turn_id,
        proposal_id=f"proposal-{turn_id}",
        source=source,
        action_name=LAUNCH_APPLICATION_ACTION,
        arguments={"application_id": "spotify"},
        state=ProposalState.READY,
    )


if __name__ == "__main__":
    unittest.main()
