"""Convert owned provider tool proposals into untrusted Phase 8 requests."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from project_akiha.core.actions import (
    ActionRequest,
    ActionValidationError,
    ProviderActionToolCatalog,
)
from project_akiha.core.voice_session import ActionProposal, ProposalState


class ProposalTurnAuthority(Protocol):
    """Minimal active-turn authority required by the proposal gateway."""

    def accepts_callback(self, session_id: str, turn_id: str) -> bool:
        """Return whether the proposal still belongs to the active turn."""


class ProposalGatewayReason(StrEnum):
    """Privacy-safe outcome for one provider proposal conversion."""

    ACCEPTED = "accepted"
    STALE = "stale"
    DUPLICATE = "duplicate"
    NOT_READY = "not_ready"
    NOT_EXPOSED = "not_exposed"


@dataclass(frozen=True, slots=True)
class ProposalGatewayDecision:
    """Sanitized proposal decision retained without target arguments."""

    session_id: str
    turn_id: str
    proposal_id: str
    action_id: str
    accepted: bool
    reason: ProposalGatewayReason


@dataclass(frozen=True, slots=True)
class ProposalGatewayResult:
    """One decision and its transient untrusted request, when accepted."""

    decision: ProposalGatewayDecision
    request: ActionRequest | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.decision.accepted != (self.request is not None):
            raise ValueError("accepted proposal decisions require one action request.")


class ProviderActionProposalGateway:
    """Reject stale or replayed proposals before Phase 8 validation."""

    def __init__(
        self,
        catalog: ProviderActionToolCatalog,
        turn_authority: ProposalTurnAuthority,
        *,
        max_records: int = 256,
    ) -> None:
        if max_records <= 0:
            raise ValueError("proposal gateway record bound must be positive.")
        self._catalog = catalog
        self._turn_authority = turn_authority
        self._max_records = max_records
        self._lock = threading.RLock()
        self._consumed: OrderedDict[tuple[str, str, str], None] = OrderedDict()
        self._decisions: deque[ProposalGatewayDecision] = deque(maxlen=max_records)

    @property
    def decisions(self) -> tuple[ProposalGatewayDecision, ...]:
        """Return bounded sanitized history without proposal arguments."""
        with self._lock:
            return tuple(self._decisions)

    def convert(self, proposal: ActionProposal) -> ProposalGatewayResult:
        """Convert one active, ready, exposed proposal without executing it."""
        if not isinstance(proposal, ActionProposal):
            raise TypeError("provider tools require a typed ActionProposal.")

        if not self._turn_authority.accepts_callback(
            proposal.session_id,
            proposal.turn_id,
        ):
            return self._reject(proposal, ProposalGatewayReason.STALE)

        identity = (
            proposal.session_id,
            proposal.turn_id,
            proposal.proposal_id,
        )
        with self._lock:
            if identity in self._consumed:
                return self._reject_locked(
                    proposal,
                    ProposalGatewayReason.DUPLICATE,
                )
            self._consumed[identity] = None
            if len(self._consumed) > self._max_records:
                self._consumed.popitem(last=False)

            if proposal.state is not ProposalState.READY:
                return self._reject_locked(
                    proposal,
                    ProposalGatewayReason.NOT_READY,
                )
            try:
                schema = self._catalog.resolve(proposal.action_name)
            except ActionValidationError:
                return self._reject_locked(
                    proposal,
                    ProposalGatewayReason.NOT_EXPOSED,
                )

            request = ActionRequest(
                correlation_id=_correlation_id(proposal),
                action_id=schema.action_id,
                source=_provider_source(proposal.source),
                parameters=proposal.arguments,
            )
            decision = _decision(
                proposal,
                accepted=True,
                reason=ProposalGatewayReason.ACCEPTED,
            )
            self._decisions.append(decision)
            return ProposalGatewayResult(decision=decision, request=request)

    def clear(self) -> None:
        """Discard replay and diagnostic state when its owner shuts down."""
        with self._lock:
            self._consumed.clear()
            self._decisions.clear()

    def _reject(
        self,
        proposal: ActionProposal,
        reason: ProposalGatewayReason,
    ) -> ProposalGatewayResult:
        with self._lock:
            return self._reject_locked(proposal, reason)

    def _reject_locked(
        self,
        proposal: ActionProposal,
        reason: ProposalGatewayReason,
    ) -> ProposalGatewayResult:
        decision = _decision(proposal, accepted=False, reason=reason)
        self._decisions.append(decision)
        return ProposalGatewayResult(decision=decision)


def _decision(
    proposal: ActionProposal,
    *,
    accepted: bool,
    reason: ProposalGatewayReason,
) -> ProposalGatewayDecision:
    return ProposalGatewayDecision(
        session_id=proposal.session_id,
        turn_id=proposal.turn_id,
        proposal_id=proposal.proposal_id,
        action_id=proposal.action_name,
        accepted=accepted,
        reason=reason,
    )


def _correlation_id(proposal: ActionProposal) -> str:
    identity = (
        f"{proposal.session_id}\0{proposal.turn_id}\0{proposal.proposal_id}"
    ).encode()
    return f"provider-{hashlib.sha256(identity).hexdigest()[:32]}"


def _provider_source(source: str) -> str:
    candidate = f"provider.{source.lower().replace(':', '.')}"
    if len(candidate) <= 64:
        return candidate
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
    return f"provider.{digest}"
