"""Privacy-safe arbitration for at-most-once assistant intent execution."""

from __future__ import annotations

import re
from collections import OrderedDict, deque
from dataclasses import dataclass, replace
from enum import IntEnum, StrEnum

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,127}$")


class IntentProposalSource(IntEnum):
    """Priority order for locally validated intent proposal sources."""

    CONFIRMATION = 1
    EXACT = 2
    CONTEXT = 3
    PROVIDER = 4


class IntentDecisionReason(StrEnum):
    """Bounded reason for one accepted or non-executed proposal."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    LOCAL_ROUTING_PENDING = "local_routing_pending"


@dataclass(frozen=True, slots=True)
class IntentProposal:
    """Sanitized proposal identity without target text or parameters."""

    turn_id: str
    proposal_id: str
    action_category: str
    source: IntentProposalSource

    def __post_init__(self) -> None:
        for value, label in (
            (self.turn_id, "intent turn ID"),
            (self.proposal_id, "intent proposal ID"),
            (self.action_category, "intent action category"),
        ):
            if not _IDENTIFIER_PATTERN.fullmatch(value):
                raise ValueError(f"{label} contains invalid characters.")


@dataclass(frozen=True, slots=True)
class IntentDecision:
    """One privacy-safe arbitration outcome."""

    turn_id: str
    proposal_id: str
    action_category: str
    source: IntentProposalSource
    accepted: bool
    reason: IntentDecisionReason
    accepted_proposal_id: str = ""


@dataclass(frozen=True, slots=True)
class IntentTurnRecord:
    """Bounded ledger state for one user intent turn."""

    turn_id: str
    local_routing_complete: bool = False
    accepted_proposal_id: str = ""
    accepted_action_category: str = ""
    accepted_source: IntentProposalSource | None = None


class IntentTurnLedger:
    """Retain bounded turn decisions without retaining user content."""

    def __init__(self, *, max_turns: int = 128, max_decisions: int = 256) -> None:
        if max_turns <= 0 or max_decisions <= 0:
            raise ValueError("intent ledger bounds must be positive.")
        self._max_turns = max_turns
        self._turns: OrderedDict[str, IntentTurnRecord] = OrderedDict()
        self._decisions: deque[IntentDecision] = deque(maxlen=max_decisions)

    @property
    def decisions(self) -> tuple[IntentDecision, ...]:
        return tuple(self._decisions)

    def get(self, turn_id: str) -> IntentTurnRecord | None:
        return self._turns.get(turn_id)

    def ensure_turn(self, turn_id: str) -> IntentTurnRecord:
        self._validate_turn_id(turn_id)
        record = self._turns.get(turn_id)
        if record is not None:
            self._turns.move_to_end(turn_id)
            return record
        record = IntentTurnRecord(turn_id=turn_id)
        self._turns[turn_id] = record
        while len(self._turns) > self._max_turns:
            self._turns.popitem(last=False)
        return record

    def replace(self, record: IntentTurnRecord) -> None:
        self._validate_turn_id(record.turn_id)
        self._turns[record.turn_id] = record
        self._turns.move_to_end(record.turn_id)

    def append_decision(self, decision: IntentDecision) -> None:
        self._decisions.append(decision)

    def clear(self) -> None:
        self._turns.clear()
        self._decisions.clear()

    @staticmethod
    def _validate_turn_id(turn_id: str) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(turn_id):
            raise ValueError("intent turn ID contains invalid characters.")


class IntentArbiter:
    """Gate provider proposals behind local routing and accept at most one."""

    def __init__(self, ledger: IntentTurnLedger | None = None) -> None:
        self._ledger = ledger or IntentTurnLedger()

    @property
    def ledger(self) -> IntentTurnLedger:
        return self._ledger

    def resolve_local(self, proposal: IntentProposal) -> IntentDecision:
        """Close local routing with one exact, contextual, or confirmation intent."""
        if proposal.source is IntentProposalSource.PROVIDER:
            raise ValueError("provider proposals require resolve_provider().")
        record = self._ledger.ensure_turn(proposal.turn_id)
        if not record.local_routing_complete:
            record = replace(record, local_routing_complete=True)
            self._ledger.replace(record)
        return self._decide(record, proposal)

    def complete_local_routing(self, turn_id: str) -> None:
        """Record that deterministic routing found no executable proposal."""
        record = self._ledger.ensure_turn(turn_id)
        if not record.local_routing_complete:
            self._ledger.replace(replace(record, local_routing_complete=True))

    def resolve_provider(self, proposal: IntentProposal) -> IntentDecision:
        """Accept a provider proposal only after deterministic routing finishes."""
        if proposal.source is not IntentProposalSource.PROVIDER:
            raise ValueError("local proposals require resolve_local().")
        record = self._ledger.ensure_turn(proposal.turn_id)
        if not record.local_routing_complete:
            decision = self._decision(
                proposal,
                accepted=False,
                reason=IntentDecisionReason.LOCAL_ROUTING_PENDING,
                accepted_proposal_id=record.accepted_proposal_id,
            )
            self._ledger.append_decision(decision)
            return decision
        return self._decide(record, proposal)

    def clear(self) -> None:
        self._ledger.clear()

    def _decide(
        self,
        record: IntentTurnRecord,
        proposal: IntentProposal,
    ) -> IntentDecision:
        if record.accepted_proposal_id:
            reason = (
                IntentDecisionReason.DUPLICATE
                if record.accepted_action_category == proposal.action_category
                else IntentDecisionReason.CONFLICT
            )
            decision = self._decision(
                proposal,
                accepted=False,
                reason=reason,
                accepted_proposal_id=record.accepted_proposal_id,
            )
            self._ledger.append_decision(decision)
            return decision

        accepted_record = replace(
            record,
            accepted_proposal_id=proposal.proposal_id,
            accepted_action_category=proposal.action_category,
            accepted_source=proposal.source,
        )
        self._ledger.replace(accepted_record)
        decision = self._decision(
            proposal,
            accepted=True,
            reason=IntentDecisionReason.ACCEPTED,
            accepted_proposal_id=proposal.proposal_id,
        )
        self._ledger.append_decision(decision)
        return decision

    @staticmethod
    def _decision(
        proposal: IntentProposal,
        *,
        accepted: bool,
        reason: IntentDecisionReason,
        accepted_proposal_id: str,
    ) -> IntentDecision:
        return IntentDecision(
            turn_id=proposal.turn_id,
            proposal_id=proposal.proposal_id,
            action_category=proposal.action_category,
            source=proposal.source,
            accepted=accepted,
            reason=reason,
            accepted_proposal_id=accepted_proposal_id,
        )
