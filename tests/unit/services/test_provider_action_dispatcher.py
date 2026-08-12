"""Tests for permission-gated provider action dispatch and sanitization."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.actions import (
    ActionPermissionPolicy,
    ActionRequestValidator,
    ActionResult,
    ActionStatus,
    FileSearchMatch,
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
from project_akiha.services.intent_arbitration import (
    IntentArbiter,
    IntentDecisionReason,
    IntentProposalSource,
)
from project_akiha.services.provider_action_dispatcher import (
    ProviderActionDispatcher,
)
from project_akiha.services.provider_action_proposal_gateway import (
    ProviderActionProposalGateway,
)


class ProviderActionDispatcherTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "session-1"
        )
        self.coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
        self.coordinator.activate()
        self.turn = self.coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        self.gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(build_default_action_registry()),
            self.coordinator,
        )
        self.action_service = _ActionService()
        self.dispatcher = ProviderActionDispatcher(
            self.action_service,
            self.coordinator,
            IntentArbiter(),
        )

    def test_provider_waits_until_local_routing_completes(self) -> None:
        conversion = self._conversion()

        result = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertEqual(result.status, ActionStatus.UNAVAILABLE.value)
        self.assertEqual(result.message, "Local intent routing has not completed.")
        self.assertEqual(self.action_service.calls, [])

    def test_permission_denial_is_sanitized_without_metadata_or_summary(self) -> None:
        conversion = self._conversion()
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.results.append(
            _action_result(
                conversion,
                status=ActionStatus.DENIED,
                summary=r"Permission missing for C:\Users\Private\secret.txt",
                metadata={"credential": "private-token"},
                permission=PermissionDecision.MISSING,
            )
        )

        result = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertEqual(result.status, ActionStatus.DENIED.value)
        self.assertEqual(
            result.message,
            "The action was denied by Akiha's permission policy.",
        )
        self.assertNotIn("secret", repr(result).casefold())
        self.assertNotIn("token", repr(result).casefold())
        self.assertFalse(self.action_service.calls[0][1])

    def test_success_discards_executor_metadata_and_raw_summary(self) -> None:
        conversion = self._conversion()
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.results.append(
            _action_result(
                conversion,
                status=ActionStatus.SUCCESS,
                summary="Opened a private local target.",
                metadata={"opened_directory": r"C:\Users\Private"},
            )
        )

        result = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertEqual(result.message, "The approved action completed.")
        self.assertFalse(hasattr(result, "metadata"))
        self.assertNotIn("private", repr(result).casefold())

    def test_search_results_reach_only_local_callback(self) -> None:
        conversion = self._conversion(action_name="files.search")
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        match = FileSearchMatch(
            name="avatar.mp4",
            path=r"C:\Users\Private\Downloads\Video\avatar.mp4",
            size_bytes=1024,
            modified_at="2026-08-12T00:00:00+00:00",
        )
        self.action_service.results.append(
            _action_result(
                conversion,
                status=ActionStatus.SUCCESS,
                summary="Found one private local media file.",
                metadata={"matches": (match,)},
            )
        )
        local_results: list[tuple[object, ActionResult]] = []

        result = asyncio.run(
            self.dispatcher.dispatch(
                conversion,
                on_local_result=lambda request, local_result: local_results.append(
                    (request, local_result)
                ),
            )
        )

        self.assertEqual(local_results[0][1].metadata["matches"], (match,))
        self.assertEqual(result.message, "The approved action completed.")
        self.assertFalse(hasattr(result, "metadata"))
        self.assertNotIn("avatar", repr(result).casefold())
        self.assertNotIn("private", repr(result).casefold())

    def test_confirmation_requires_one_separate_trusted_resolution(self) -> None:
        conversion = self._conversion(action_name="files.open")
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.results.extend(
            (
                _action_result(
                    conversion,
                    status=ActionStatus.CONFIRMATION_REQUIRED,
                    summary="Confirmation required.",
                    permission=PermissionDecision.CONFIRMATION_REQUIRED,
                ),
                _action_result(
                    conversion,
                    status=ActionStatus.SUCCESS,
                    summary="Opened.",
                    permission=PermissionDecision.GRANTED,
                ),
            )
        )

        pending = asyncio.run(self.dispatcher.dispatch(conversion))
        confirmation = self.dispatcher.pending_confirmation(
            session_id=self.turn.session_id,
            turn_id=self.turn.turn_id,
            proposal_id=conversion.decision.proposal_id,
        )
        assert confirmation is not None
        self.assertEqual(confirmation.action_id, "files.open")
        self.assertIn(r"C:\Users\Private\notes.txt", confirmation.prompt)
        confirmed = asyncio.run(
            self.dispatcher.resolve_confirmation(
                session_id=self.turn.session_id,
                turn_id=self.turn.turn_id,
                proposal_id=conversion.decision.proposal_id,
                approved=True,
            )
        )
        replay = asyncio.run(
            self.dispatcher.resolve_confirmation(
                session_id=self.turn.session_id,
                turn_id=self.turn.turn_id,
                proposal_id=conversion.decision.proposal_id,
                approved=True,
            )
        )

        self.assertEqual(pending.status, ActionStatus.CONFIRMATION_REQUIRED.value)
        self.assertEqual(confirmed.status, ActionStatus.SUCCESS.value)
        self.assertEqual(replay.status, ActionStatus.UNAVAILABLE.value)
        self.assertEqual(
            [confirmed for _, confirmed in self.action_service.calls],
            [False, True],
        )
        self.assertEqual(self.dispatcher.pending_confirmation_count, 0)

    def test_declined_confirmation_never_calls_action_service_again(self) -> None:
        conversion = self._conversion(action_name="files.open")
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.results.append(
            _action_result(
                conversion,
                status=ActionStatus.CONFIRMATION_REQUIRED,
                summary="Confirmation required.",
                permission=PermissionDecision.CONFIRMATION_REQUIRED,
            )
        )
        asyncio.run(self.dispatcher.dispatch(conversion))

        declined = asyncio.run(
            self.dispatcher.resolve_confirmation(
                session_id=self.turn.session_id,
                turn_id=self.turn.turn_id,
                proposal_id=conversion.decision.proposal_id,
                approved=False,
            )
        )

        self.assertEqual(declined.status, ActionStatus.DENIED.value)
        self.assertEqual(len(self.action_service.calls), 1)

    def test_stale_confirmation_cannot_execute(self) -> None:
        conversion = self._conversion(action_name="files.open")
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.results.append(
            _action_result(
                conversion,
                status=ActionStatus.CONFIRMATION_REQUIRED,
                summary="Confirmation required.",
                permission=PermissionDecision.CONFIRMATION_REQUIRED,
            )
        )
        asyncio.run(self.dispatcher.dispatch(conversion))
        self.coordinator.complete_turn(self.turn.session_id, self.turn.turn_id)

        stale = asyncio.run(
            self.dispatcher.resolve_confirmation(
                session_id=self.turn.session_id,
                turn_id=self.turn.turn_id,
                proposal_id=conversion.decision.proposal_id,
                approved=True,
            )
        )

        self.assertEqual(stale.status, ActionStatus.CANCELLED.value)
        self.assertEqual(len(self.action_service.calls), 1)
        self.assertEqual(self.dispatcher.pending_confirmation_count, 0)

    def test_local_action_claim_blocks_conflicting_provider_execution(self) -> None:
        conversion = self._conversion()
        local = self.dispatcher.claim_local_action(
            session_id=self.turn.session_id,
            turn_id=self.turn.turn_id,
            proposal_id="local-proposal-1",
            action_id="spotify.pause",
            source=IntentProposalSource.EXACT,
        )

        provider = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertTrue(local.accepted)
        self.assertEqual(local.reason, IntentDecisionReason.ACCEPTED)
        self.assertEqual(provider.status, ActionStatus.DENIED.value)
        self.assertEqual(self.action_service.calls, [])

    def test_stale_conversion_stops_before_action_service(self) -> None:
        conversion = self._conversion()
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.coordinator.complete_turn(self.turn.session_id, self.turn.turn_id)

        result = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertEqual(result.status, ActionStatus.CANCELLED.value)
        self.assertEqual(self.action_service.calls, [])

    def test_service_failure_returns_only_bounded_provider_failure(self) -> None:
        conversion = self._conversion()
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.failure = RuntimeError(
            r"database failed at C:\Users\Private\actions.db"
        )

        result = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertEqual(result.status, ActionStatus.FAILED.value)
        self.assertEqual(result.message, "The approved action failed safely.")
        self.assertNotIn("database", repr(result).casefold())

    def test_mismatched_service_result_fails_closed(self) -> None:
        conversion = self._conversion()
        self.dispatcher.complete_local_routing(
            self.turn.session_id,
            self.turn.turn_id,
        )
        self.action_service.results.append(
            ActionResult(
                correlation_id="different-request",
                action_id="applications.close",
                status=ActionStatus.SUCCESS,
                summary="Wrong result.",
                permission_decision=PermissionDecision.GRANTED,
            )
        )

        result = asyncio.run(self.dispatcher.dispatch(conversion))

        self.assertEqual(result.status, ActionStatus.FAILED.value)
        self.assertEqual(result.message, "The approved action failed safely.")

    def test_rejected_gateway_result_cannot_enter_dispatch(self) -> None:
        rejected = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="system.run",
            )
        )

        with self.assertRaisesRegex(ValueError, "accepted proposal"):
            asyncio.run(self.dispatcher.dispatch(rejected))

    def test_real_phase8_service_denies_and_audits_missing_permission(self) -> None:
        with TemporaryDirectory() as directory:
            path_policy = ProtectedPathPolicy()
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            registry = build_default_action_registry()
            action_service = AssistantActionService(
                ActionRequestValidator(registry, path_policy),
                ActionPermissionPolicy(path_policy),
                repository,
                repository,
            )
            dispatcher = ProviderActionDispatcher(
                action_service,
                self.coordinator,
                IntentArbiter(),
            )
            conversion = self._conversion()
            dispatcher.complete_local_routing(
                self.turn.session_id,
                self.turn.turn_id,
            )

            result = asyncio.run(dispatcher.dispatch(conversion))
            audits = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(result.status, ActionStatus.DENIED.value)
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].source, "provider.gemini.live")
        self.assertEqual(audits[0].result_status, ActionStatus.DENIED)
        self.assertEqual(
            audits[0].permission_decision,
            PermissionDecision.MISSING,
        )

    def _conversion(self, *, action_name: str = "applications.launch"):
        if action_name == "files.open":
            arguments = {"path": r"C:\Users\Private\notes.txt"}
        elif action_name == "files.search":
            arguments = {
                "root": r"C:\Users\Private\Downloads\Video",
                "query": "avatar",
                "media_only": True,
                "result_mode": "open_unique",
                "relaxed": True,
            }
        else:
            arguments = {"application_id": "spotify"}
        return self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name=action_name,
                arguments=arguments,
            )
        )


class _ActionService:
    def __init__(self) -> None:
        self.results: list[ActionResult] = []
        self.calls: list[tuple[object, bool]] = []
        self.failure: Exception | None = None

    async def evaluate_request(
        self,
        request,
        *,
        confirmed: bool = False,
        cancellation_token=None,
    ) -> ActionResult:
        del cancellation_token
        self.calls.append((request, confirmed))
        if self.failure is not None:
            raise self.failure
        return self.results.pop(0)


def _proposal(
    session_id: str,
    turn_id: str,
    *,
    action_name: str,
    arguments: dict[str, object] | None = None,
) -> ActionProposal:
    return ActionProposal(
        session_id=session_id,
        turn_id=turn_id,
        proposal_id="provider-proposal-1",
        source="gemini.live",
        action_name=action_name,
        arguments=arguments or {"application_id": "spotify"},
        state=ProposalState.READY,
    )


def _action_result(
    conversion,
    *,
    status: ActionStatus,
    summary: str,
    metadata: dict[str, object] | None = None,
    permission: PermissionDecision = PermissionDecision.GRANTED,
) -> ActionResult:
    assert conversion.request is not None
    return ActionResult(
        correlation_id=conversion.request.correlation_id,
        action_id=conversion.request.action_id,
        status=status,
        summary=summary,
        permission_decision=permission,
        metadata=metadata or {},
    )


if __name__ == "__main__":
    unittest.main()
