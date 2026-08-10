"""Tests for the untrusted provider proposal-to-request gateway."""

from __future__ import annotations

import unittest

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionRequestValidator,
    ActionValidationError,
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
from project_akiha.services.provider_action_proposal_gateway import (
    ProposalGatewayReason,
    ProviderActionProposalGateway,
)


class ProviderActionProposalGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_action_registry()
        self.coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "session-1"
        )
        self.coordinator.request_start(VoiceProcessingMode.HOSTED_LIVE)
        self.coordinator.activate()
        self.turn = self.coordinator.begin_turn(VoiceInputMode.HOSTED_LIVE_CONVERSATION)
        self.gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(self.registry),
            self.coordinator,
            max_records=3,
        )

    def test_converts_owned_ready_proposal_to_untrusted_action_request(self) -> None:
        result = self.gateway.convert(
            _proposal(self.turn.session_id, self.turn.turn_id)
        )

        self.assertTrue(result.decision.accepted)
        self.assertEqual(result.decision.reason, ProposalGatewayReason.ACCEPTED)
        assert result.request is not None
        self.assertEqual(result.request.action_id, "applications.launch")
        self.assertEqual(result.request.source, "provider.gemini.live")
        self.assertEqual(result.request.parameters, {"application_id": "spotify"})
        self.assertNotIn("spotify", repr(result))
        self.assertFalse(hasattr(self.gateway.decisions[0], "parameters"))

    def test_rejects_wrong_session_and_completed_turn_as_stale(self) -> None:
        wrong_session = self.gateway.convert(_proposal("session-2", self.turn.turn_id))
        self.coordinator.complete_turn(self.turn.session_id, self.turn.turn_id)
        completed_turn = self.gateway.convert(
            _proposal(self.turn.session_id, self.turn.turn_id, proposal_id="proposal-2")
        )

        self.assertEqual(wrong_session.decision.reason, ProposalGatewayReason.STALE)
        self.assertEqual(completed_turn.decision.reason, ProposalGatewayReason.STALE)
        self.assertIsNone(wrong_session.request)
        self.assertIsNone(completed_turn.request)

    def test_rejects_duplicate_proposal_identity(self) -> None:
        proposal = _proposal(self.turn.session_id, self.turn.turn_id)

        accepted = self.gateway.convert(proposal)
        duplicate = self.gateway.convert(proposal)

        self.assertTrue(accepted.decision.accepted)
        self.assertFalse(duplicate.decision.accepted)
        self.assertEqual(duplicate.decision.reason, ProposalGatewayReason.DUPLICATE)

    def test_rejects_ambiguous_and_unexposed_proposals(self) -> None:
        ambiguous = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                state=ProposalState.AMBIGUOUS,
            )
        )
        unexposed = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                proposal_id="proposal-2",
                action_name="system.run",
            )
        )

        self.assertEqual(ambiguous.decision.reason, ProposalGatewayReason.NOT_READY)
        self.assertEqual(unexposed.decision.reason, ProposalGatewayReason.NOT_EXPOSED)

    def test_invalid_parameters_remain_for_phase8_validator(self) -> None:
        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                arguments={"application_id": "notepad"},
            )
        )
        assert result.request is not None

        validator = ActionRequestValidator(self.registry, ProtectedPathPolicy())
        with self.assertRaises(ActionValidationError) as captured:
            validator.validate(result.request)

        self.assertEqual(
            captured.exception.category,
            ActionFailureCategory.INVALID_PARAMETERS,
        )

    def test_history_is_bounded_and_clear_discards_replay_state(self) -> None:
        for index in range(4):
            self.gateway.convert(
                _proposal(
                    self.turn.session_id,
                    self.turn.turn_id,
                    proposal_id=f"proposal-{index}",
                    action_name="system.run",
                )
            )

        self.assertEqual(len(self.gateway.decisions), 3)
        self.gateway.clear()
        self.assertEqual(self.gateway.decisions, ())

        accepted = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                proposal_id="proposal-3",
            )
        )
        self.assertTrue(accepted.decision.accepted)


def _proposal(
    session_id: str,
    turn_id: str,
    *,
    proposal_id: str = "proposal-1",
    action_name: str = "applications.launch",
    arguments: dict[str, object] | None = None,
    state: ProposalState = ProposalState.READY,
) -> ActionProposal:
    return ActionProposal(
        session_id=session_id,
        turn_id=turn_id,
        proposal_id=proposal_id,
        source="gemini.live",
        action_name=action_name,
        arguments=arguments or {"application_id": "spotify"},
        state=state,
    )


if __name__ == "__main__":
    unittest.main()
