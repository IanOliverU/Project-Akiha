"""Tests for privacy-safe at-most-once intent arbitration."""

from __future__ import annotations

import unittest

from project_akiha.services.intent_arbitration import (
    IntentArbiter,
    IntentDecisionReason,
    IntentProposal,
    IntentProposalSource,
    IntentTurnLedger,
)


class IntentArbiterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = IntentTurnLedger(max_turns=3, max_decisions=4)
        self.arbiter = IntentArbiter(self.ledger)

    def test_accepts_one_local_proposal_and_records_sanitized_identity(self) -> None:
        decision = self.arbiter.resolve_local(
            _proposal("turn-1", "proposal-1", "applications.launch")
        )

        self.assertTrue(decision.accepted)
        self.assertEqual(decision.reason, IntentDecisionReason.ACCEPTED)
        record = self.ledger.get("turn-1")
        self.assertTrue(record.local_routing_complete)
        self.assertEqual(record.accepted_action_category, "applications.launch")
        self.assertFalse(hasattr(record, "parameters"))
        self.assertFalse(hasattr(record, "text"))

    def test_rejects_duplicate_and_conflicting_proposals_for_same_turn(self) -> None:
        self.arbiter.resolve_local(
            _proposal("turn-1", "proposal-1", "applications.launch")
        )

        duplicate = self.arbiter.resolve_local(
            _proposal(
                "turn-1",
                "proposal-2",
                "applications.launch",
                IntentProposalSource.CONTEXT,
            )
        )
        conflict = self.arbiter.resolve_provider(
            _proposal(
                "turn-1",
                "proposal-3",
                "applications.close",
                IntentProposalSource.PROVIDER,
            )
        )

        self.assertFalse(duplicate.accepted)
        self.assertEqual(duplicate.reason, IntentDecisionReason.DUPLICATE)
        self.assertFalse(conflict.accepted)
        self.assertEqual(conflict.reason, IntentDecisionReason.CONFLICT)
        self.assertEqual(conflict.accepted_proposal_id, "proposal-1")

    def test_provider_cannot_win_before_local_routing_completes(self) -> None:
        pending = self.arbiter.resolve_provider(
            _proposal(
                "turn-2",
                "provider-1",
                "applications.launch",
                IntentProposalSource.PROVIDER,
            )
        )

        self.assertFalse(pending.accepted)
        self.assertEqual(
            pending.reason,
            IntentDecisionReason.LOCAL_ROUTING_PENDING,
        )

        self.arbiter.complete_local_routing("turn-2")
        accepted = self.arbiter.resolve_provider(
            _proposal(
                "turn-2",
                "provider-1",
                "applications.launch",
                IntentProposalSource.PROVIDER,
            )
        )
        self.assertTrue(accepted.accepted)

    def test_source_priority_is_explicit_and_stable(self) -> None:
        self.assertLess(IntentProposalSource.CONFIRMATION, IntentProposalSource.EXACT)
        self.assertLess(IntentProposalSource.EXACT, IntentProposalSource.CONTEXT)
        self.assertLess(IntentProposalSource.CONTEXT, IntentProposalSource.PROVIDER)

    def test_ledger_bounds_turns_and_decisions(self) -> None:
        for index in range(5):
            turn_id = f"turn-{index}"
            self.arbiter.resolve_local(
                _proposal(turn_id, f"proposal-{index}", "applications.launch")
            )

        self.assertIsNone(self.ledger.get("turn-0"))
        self.assertIsNone(self.ledger.get("turn-1"))
        self.assertIsNotNone(self.ledger.get("turn-4"))
        self.assertEqual(len(self.ledger.decisions), 4)

    def test_clear_discards_turn_and_decision_history(self) -> None:
        self.arbiter.resolve_local(
            _proposal("turn-1", "proposal-1", "applications.launch")
        )

        self.arbiter.clear()

        self.assertIsNone(self.ledger.get("turn-1"))
        self.assertEqual(self.ledger.decisions, ())

    def test_rejects_wrong_resolution_lane_and_invalid_identifiers(self) -> None:
        with self.assertRaises(ValueError):
            self.arbiter.resolve_local(
                _proposal(
                    "turn-1",
                    "provider-1",
                    "applications.launch",
                    IntentProposalSource.PROVIDER,
                )
            )
        with self.assertRaises(ValueError):
            IntentProposal(
                turn_id="bad turn",
                proposal_id="proposal-1",
                action_category="applications.launch",
                source=IntentProposalSource.EXACT,
            )


def _proposal(
    turn_id: str,
    proposal_id: str,
    action_category: str,
    source: IntentProposalSource = IntentProposalSource.EXACT,
) -> IntentProposal:
    return IntentProposal(
        turn_id=turn_id,
        proposal_id=proposal_id,
        action_category=action_category,
        source=source,
    )


if __name__ == "__main__":
    unittest.main()
