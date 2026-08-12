"""Permission-gated dispatch for accepted provider action proposals."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    ActionResult,
    ActionStatus,
    PermissionDecision,
)
from project_akiha.core.voice_session import SanitizedActionResult
from project_akiha.services.intent_arbitration import (
    IntentArbiter,
    IntentDecision,
    IntentDecisionReason,
    IntentProposal,
    IntentProposalSource,
)
from project_akiha.services.provider_action_proposal_gateway import (
    ProposalGatewayDecision,
    ProposalGatewayResult,
    ProposalTurnAuthority,
)


@dataclass(frozen=True, slots=True)
class ProviderActionConfirmation:
    """Trusted local-only confirmation description never sent to a provider."""

    session_id: str
    turn_id: str
    proposal_id: str
    action_id: str
    prompt: str


class ProviderActionService(Protocol):
    """Existing Phase 8 action-service surface used by provider dispatch."""

    async def evaluate_request(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> ActionResult:
        """Validate, authorize, execute, and audit one typed request."""


class ProviderActionDispatcher:
    """Reuse Phase 8 policy without exposing it to a provider adapter."""

    def __init__(
        self,
        action_service: ProviderActionService,
        turn_authority: ProposalTurnAuthority,
        intent_arbiter: IntentArbiter,
        *,
        max_pending_confirmations: int = 32,
    ) -> None:
        if max_pending_confirmations <= 0:
            raise ValueError("pending confirmation bound must be positive.")
        self._action_service = action_service
        self._turn_authority = turn_authority
        self._intent_arbiter = intent_arbiter
        self._max_pending_confirmations = max_pending_confirmations
        self._lock = threading.RLock()
        self._pending: OrderedDict[
            tuple[str, str, str],
            ActionRequest,
        ] = OrderedDict()

    @property
    def pending_confirmation_count(self) -> int:
        """Return only a count; pending request arguments remain private."""
        with self._lock:
            return len(self._pending)

    def complete_local_routing(self, session_id: str, turn_id: str) -> None:
        """Declare that deterministic routing found no action for this turn."""
        with self._lock:
            self._intent_arbiter.complete_local_routing(
                _arbitration_turn_id(session_id, turn_id)
            )

    def claim_local_action(
        self,
        *,
        session_id: str,
        turn_id: str,
        proposal_id: str,
        action_id: str,
        source: IntentProposalSource,
    ) -> IntentDecision:
        """Reserve a deterministic action before any provider proposal."""
        if source is IntentProposalSource.PROVIDER:
            raise ValueError("provider proposals require dispatch().")
        if not self._turn_authority.accepts_callback(session_id, turn_id):
            raise ValueError("local action claims require an active voice turn.")
        proposal = IntentProposal(
            turn_id=_arbitration_turn_id(session_id, turn_id),
            proposal_id=_arbitration_proposal_id(
                session_id,
                turn_id,
                proposal_id,
            ),
            action_category=action_id,
            source=source,
        )
        with self._lock:
            return self._intent_arbiter.resolve_local(proposal)

    async def dispatch(
        self,
        conversion: ProposalGatewayResult,
        *,
        on_local_result: Callable[[ActionRequest, ActionResult], None] | None = None,
    ) -> SanitizedActionResult:
        """Dispatch a proposal and optionally present its raw result locally."""
        decision, request = _require_accepted_conversion(conversion)
        if not self._turn_authority.accepts_callback(
            decision.session_id,
            decision.turn_id,
        ):
            return _sanitized(
                conversion,
                status=ActionStatus.CANCELLED.value,
                message="The action proposal is no longer active.",
            )

        provider_proposal = IntentProposal(
            turn_id=_arbitration_turn_id(
                decision.session_id,
                decision.turn_id,
            ),
            proposal_id=_arbitration_proposal_id(
                decision.session_id,
                decision.turn_id,
                decision.proposal_id,
            ),
            action_category=decision.action_id,
            source=IntentProposalSource.PROVIDER,
        )
        with self._lock:
            arbitration = self._intent_arbiter.resolve_provider(provider_proposal)
        if not arbitration.accepted:
            return _arbitration_result(conversion, arbitration.reason)

        result = await self._evaluate(request, confirmed=False)
        if on_local_result is not None and (
            "matches" in result.metadata or "track_candidates" in result.metadata
        ):
            on_local_result(request, result)
        if result.status is ActionStatus.CONFIRMATION_REQUIRED:
            self._remember_pending(conversion, request)
        return _sanitize_action_result(conversion, result)

    async def resolve_confirmation(
        self,
        *,
        session_id: str,
        turn_id: str,
        proposal_id: str,
        approved: bool,
    ) -> SanitizedActionResult:
        """Resolve one pending action from a trusted local confirmation UI."""
        if not isinstance(approved, bool):
            raise TypeError("provider action confirmation must be boolean.")
        key = (session_id, turn_id, proposal_id)
        with self._lock:
            request = self._pending.pop(key, None)
        if request is None:
            return SanitizedActionResult(
                session_id=session_id,
                turn_id=turn_id,
                proposal_id=proposal_id,
                status=ActionStatus.UNAVAILABLE.value,
                message="No pending action confirmation is available.",
            )
        if not approved:
            return SanitizedActionResult(
                session_id=session_id,
                turn_id=turn_id,
                proposal_id=proposal_id,
                status=ActionStatus.DENIED.value,
                message="The user declined the action.",
            )
        if not self._turn_authority.accepts_callback(session_id, turn_id):
            return SanitizedActionResult(
                session_id=session_id,
                turn_id=turn_id,
                proposal_id=proposal_id,
                status=ActionStatus.CANCELLED.value,
                message="The action proposal is no longer active.",
            )

        result = await self._evaluate(request, confirmed=True)
        return SanitizedActionResult(
            session_id=session_id,
            turn_id=turn_id,
            proposal_id=proposal_id,
            status=result.status.value,
            message=_safe_message(result.status),
        )

    def clear(self) -> None:
        """Discard pending sensitive arguments during shutdown or lane change."""
        with self._lock:
            self._pending.clear()

    def pending_confirmation(
        self,
        *,
        session_id: str,
        turn_id: str,
        proposal_id: str,
    ) -> ProviderActionConfirmation | None:
        """Return a local UI description without consuming the pending request."""
        key = (session_id, turn_id, proposal_id)
        with self._lock:
            request = self._pending.get(key)
        if request is None:
            return None
        return ProviderActionConfirmation(
            session_id=session_id,
            turn_id=turn_id,
            proposal_id=proposal_id,
            action_id=request.action_id,
            prompt=_confirmation_prompt(request),
        )

    async def _evaluate(
        self,
        request: ActionRequest,
        *,
        confirmed: bool,
    ) -> ActionResult:
        try:
            result = await self._action_service.evaluate_request(
                request,
                confirmed=confirmed,
            )
        except Exception:
            return _failed_action_result(request)
        if not isinstance(result, ActionResult):
            return _failed_action_result(request)
        if (
            result.correlation_id != request.correlation_id
            or result.action_id != request.action_id
        ):
            return _failed_action_result(request)
        return result

    def _remember_pending(
        self,
        conversion: ProposalGatewayResult,
        request: ActionRequest,
    ) -> None:
        decision = conversion.decision
        key = (
            decision.session_id,
            decision.turn_id,
            decision.proposal_id,
        )
        with self._lock:
            self._pending[key] = request
            self._pending.move_to_end(key)
            while len(self._pending) > self._max_pending_confirmations:
                self._pending.popitem(last=False)


def _require_accepted_conversion(
    conversion: ProposalGatewayResult,
) -> tuple[ProposalGatewayDecision, ActionRequest]:
    if not isinstance(conversion, ProposalGatewayResult):
        raise TypeError("provider dispatch requires a ProposalGatewayResult.")
    if not conversion.decision.accepted or conversion.request is None:
        raise ValueError("provider dispatch requires an accepted proposal conversion.")
    return conversion.decision, conversion.request


def _sanitize_action_result(
    conversion: ProposalGatewayResult,
    result: ActionResult,
) -> SanitizedActionResult:
    return _sanitized(
        conversion,
        status=result.status.value,
        message=_safe_message(result.status),
    )


def _sanitized(
    conversion: ProposalGatewayResult,
    *,
    status: str,
    message: str,
) -> SanitizedActionResult:
    decision = conversion.decision
    return SanitizedActionResult(
        session_id=decision.session_id,
        turn_id=decision.turn_id,
        proposal_id=decision.proposal_id,
        status=status,
        message=message,
    )


def _arbitration_result(
    conversion: ProposalGatewayResult,
    reason: IntentDecisionReason,
) -> SanitizedActionResult:
    if reason is IntentDecisionReason.LOCAL_ROUTING_PENDING:
        return _sanitized(
            conversion,
            status=ActionStatus.UNAVAILABLE.value,
            message="Local intent routing has not completed.",
        )
    return _sanitized(
        conversion,
        status=ActionStatus.DENIED.value,
        message="Another action proposal already owns this turn.",
    )


def _safe_message(status: ActionStatus) -> str:
    return {
        ActionStatus.SUCCESS: "The approved action completed.",
        ActionStatus.DENIED: "The action was denied by Akiha's permission policy.",
        ActionStatus.CANCELLED: "The action was cancelled.",
        ActionStatus.CONFIRMATION_REQUIRED: (
            "The action is waiting for current user confirmation."
        ),
        ActionStatus.UNAVAILABLE: "The approved action is currently unavailable.",
        ActionStatus.TIMED_OUT: "The approved action timed out.",
        ActionStatus.FAILED: "The approved action failed safely.",
    }[status]


def _failed_action_result(request: ActionRequest) -> ActionResult:
    return ActionResult(
        correlation_id=request.correlation_id,
        action_id=request.action_id,
        status=ActionStatus.FAILED,
        summary="The assistant action could not be completed.",
        permission_decision=PermissionDecision.NOT_EVALUATED,
    )


def _confirmation_prompt(request: ActionRequest) -> str:
    if request.action_id == "files.open":
        target = request.parameters.get("path")
        if isinstance(target, str) and target.strip():
            return (
                "Open this passive file with its default application?\n\n"
                + target.strip()
            )
    return f"Allow Akiha to perform this action?\n\n{request.action_id}"


def _arbitration_turn_id(session_id: str, turn_id: str) -> str:
    return f"provider-turn-{_identity_digest(session_id, turn_id)}"


def _arbitration_proposal_id(
    session_id: str,
    turn_id: str,
    proposal_id: str,
) -> str:
    return f"provider-proposal-{_identity_digest(session_id, turn_id, proposal_id)}"


def _identity_digest(*parts: str) -> str:
    payload = "\0".join(parts).encode()
    return hashlib.sha256(payload).hexdigest()[:32]
