"""Final-transcript bridge to Akiha's real typed-action boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from project_akiha.core.actions import (
    CLOSE_APPLICATION_ACTION,
    LAUNCH_APPLICATION_ACTION,
    ActionCancellationToken,
    ActionRequest,
)
from project_akiha.services.assistant_action_bridge import (
    AssistantActionBridge,
    AssistantActionDispatch,
)
from project_akiha.services.assistant_tool_gateway import (
    AssistantToolKind,
    AssistantToolProposal,
    LLMAssistantToolGateway,
)
from spikes.voice_pipeline.pipeline_spike import TranscriptRevision


@dataclass(frozen=True, slots=True)
class ActionGatewayProbeOutcome:
    """One validated proposal and its optional local action dispatch."""

    proposal: AssistantToolProposal
    dispatch: AssistantActionDispatch | None = None


class TypedActionGatewayProbe:
    """Commit final speech through the provider-neutral action boundary."""

    def __init__(
        self,
        proposal_gateway: LLMAssistantToolGateway,
        action_bridge: AssistantActionBridge,
    ) -> None:
        self._proposal_gateway = proposal_gateway
        self._action_bridge = action_bridge
        self._committed_turns: set[int] = set()
        self._cancelled_turns: set[int] = set()
        self._tokens: dict[int, ActionCancellationToken] = {}
        self._closed = False

    def observe_partial(
        self,
        turn_id: int,
        revision: TranscriptRevision,
    ) -> None:
        """Accept speculative text without calling a provider or action service."""
        self._validate_turn_id(turn_id)
        self._require_open()
        if revision.is_final:
            raise ValueError("Partial action observation cannot accept final text.")

    async def commit_final(
        self,
        turn_id: int,
        revision: TranscriptRevision,
    ) -> ActionGatewayProbeOutcome:
        """Propose once from final text and dispatch only direct typed actions."""
        self._validate_turn_id(turn_id)
        self._require_open()
        if not revision.is_final:
            raise ValueError("Assistant actions require an authoritative final text.")
        if turn_id in self._committed_turns:
            raise RuntimeError("Assistant action turn was already committed.")
        if turn_id in self._cancelled_turns:
            raise asyncio.CancelledError
        self._committed_turns.add(turn_id)
        token = ActionCancellationToken()
        self._tokens[turn_id] = token

        try:
            proposal = await self._proposal_gateway.propose(revision.text)
            if turn_id in self._cancelled_turns or token.is_cancelled:
                raise asyncio.CancelledError
            request = _direct_action_request(turn_id, proposal)
            if request is None:
                return ActionGatewayProbeOutcome(proposal=proposal)
            dispatch = await self._action_bridge.dispatch(
                request,
                cancellation_token=token,
            )
            return ActionGatewayProbeOutcome(proposal=proposal, dispatch=dispatch)
        finally:
            self._tokens.pop(turn_id, None)

    def cancel_turn(self, turn_id: int) -> bool:
        """Invalidate a turn and cooperatively cancel any local executor."""
        self._validate_turn_id(turn_id)
        already_cancelled = turn_id in self._cancelled_turns
        self._cancelled_turns.add(turn_id)
        token = self._tokens.get(turn_id)
        if token is not None:
            token.cancel()
        return not already_cancelled

    def shutdown(self) -> None:
        """Reject new proposals and invalidate every in-flight turn."""
        if self._closed:
            return
        self._closed = True
        for turn_id in tuple(self._tokens):
            self.cancel_turn(turn_id)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Assistant action gateway probe is shut down.")

    @staticmethod
    def _validate_turn_id(turn_id: int) -> None:
        if isinstance(turn_id, bool) or not isinstance(turn_id, int) or turn_id < 1:
            raise ValueError("Assistant action turn ID must be positive.")


def _direct_action_request(
    turn_id: int,
    proposal: AssistantToolProposal,
) -> ActionRequest | None:
    if proposal.kind is AssistantToolKind.LAUNCH_APPLICATION:
        action_id = LAUNCH_APPLICATION_ACTION
    elif proposal.kind is AssistantToolKind.CLOSE_APPLICATION:
        action_id = CLOSE_APPLICATION_ACTION
    else:
        return None
    return ActionRequest(
        correlation_id=f"voice-proposal-{turn_id}",
        action_id=action_id,
        source="voice_llm_proposal",
        parameters={"application_id": proposal.application_id},
    )
