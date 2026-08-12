"""Tests for the untrusted provider proposal-to-request gateway."""

from __future__ import annotations

import unittest

from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionRequestValidator,
    ActionValidationError,
    DirectorySearchMatch,
    FileSearchMatch,
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

    def test_approved_directory_display_name_resolves_only_inside_gateway(self) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open_directory",
                arguments={"path": "Downloads folder"},
            )
        )

        self.assertTrue(result.decision.accepted)
        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {"path": r"C:\Users\Private\Downloads"},
        )
        self.assertNotIn("private", repr(result).casefold())
        self.assertNotIn("downloads", repr(self.gateway.decisions).casefold())

    def test_unknown_directory_display_name_remains_untrusted(self) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open_directory",
                arguments={"path": "System folder"},
            )
        )

        assert result.request is not None
        self.assertEqual(result.request.parameters, {"path": "System folder"})

    def test_approved_root_relative_directory_resolves_inside_gateway(self) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open_directory",
                arguments={"path": "Downloads/Videos"},
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {"path": r"C:\Users\Private\Downloads\Videos"},
        )

    def test_root_relative_directory_rejects_traversal(self) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open_directory",
                arguments={"path": "Downloads/../Windows"},
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {"path": "Downloads/../Windows"},
        )

    def test_approved_root_relative_passive_file_resolves_for_confirmation(
        self,
    ) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open",
                arguments={"path": "Downloads/Video/example.mp4"},
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {"path": r"C:\Users\Private\Downloads\Video\example.mp4"},
        )

    def test_approved_search_root_display_name_resolves_locally(self) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="directories.search",
                arguments={"root": "Downloads folder", "query": "Video"},
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {"root": r"C:\Users\Private\Downloads", "query": "Video"},
        )

    def test_approved_descendant_search_root_resolves_locally(self) -> None:
        self.gateway.set_directory_aliases({"downloads": r"C:\Users\Private\Downloads"})

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.search",
                arguments={
                    "root": "Downloads/Video",
                    "query": "avatar",
                    "media_only": True,
                    "result_mode": "open_unique",
                    "relaxed": True,
                },
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {
                "root": r"C:\Users\Private\Downloads\Video",
                "query": "avatar",
                "media_only": True,
                "result_mode": "open_unique",
                "relaxed": True,
            },
        )

    def test_numbered_file_result_resolves_to_private_local_path(self) -> None:
        self.gateway.set_file_results(
            (
                _file_match("first.mp4"),
                _file_match("second.mp4"),
            )
        )

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open",
                arguments={"path": "result 2"},
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {"path": r"C:\Users\Private\Downloads\second.mp4"},
        )
        self.assertNotIn("second", repr(result).casefold())
        self.assertNotIn("private", repr(self.gateway.decisions).casefold())

    def test_numbered_directory_result_uses_only_directory_action(self) -> None:
        self.gateway.set_directory_results(
            (
                DirectorySearchMatch(
                    name="Video",
                    path=r"C:\Users\Private\Downloads\Video",
                    modified_at="2026-08-12T00:00:00+00:00",
                ),
            )
        )

        directory = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open_directory",
                arguments={"path": "result 1"},
            )
        )

        assert directory.request is not None
        self.assertEqual(
            directory.request.parameters,
            {"path": r"C:\Users\Private\Downloads\Video"},
        )

    def test_provider_track_title_and_artist_are_normalized_locally(self) -> None:
        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="spotify.play_track",
                arguments={
                    "service": "spotify",
                    "track_query": "Hanabi by ADO",
                },
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {
                "service": "spotify",
                "track_query": "Hanabi",
                "artist_query": "ADO",
            },
        )

    def test_numbered_spotify_result_resolves_without_provider_path_data(self) -> None:
        self.gateway.set_spotify_track_results(
            (
                {
                    "service": "spotify",
                    "track_query": "Hanabi",
                    "artist_query": "ADO",
                    "track_name": "Hanabi",
                    "track_artist": "ADO",
                    "track_uri": "spotify:track:track1",
                },
            )
        )

        result = self.gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="spotify.play_track",
                arguments={"service": "spotify", "track_query": "result 1"},
            )
        )

        assert result.request is not None
        self.assertEqual(
            result.request.parameters,
            {
                "service": "spotify",
                "track_query": "Hanabi",
                "artist_query": "ADO",
                "track_name": "Hanabi",
                "track_artist": "ADO",
                "track_uri": "spotify:track:track1",
            },
        )
        self.assertNotIn("hanabi", repr(result).casefold())
        self.assertNotIn("track1", repr(self.gateway.decisions).casefold())

    def test_spotify_result_rejects_unvalidated_uri(self) -> None:
        with self.assertRaises(ValueError):
            self.gateway.set_spotify_track_results(
                (
                    {
                        "service": "spotify",
                        "track_query": "Hanabi",
                        "track_name": "Hanabi",
                        "track_uri": "https://example.invalid/track",
                    },
                )
            )

    def test_expired_or_out_of_range_result_reference_remains_untrusted(self) -> None:
        clock = [10.0]
        gateway = ProviderActionProposalGateway(
            build_default_provider_action_catalog(self.registry),
            self.coordinator,
            local_result_ttl_seconds=5.0,
            monotonic_clock=lambda: clock[0],
        )
        gateway.set_file_results((_file_match("first.mp4"),))

        out_of_range = gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                action_name="files.open",
                arguments={"path": "result 2"},
            )
        )
        clock[0] = 16.0
        expired = gateway.convert(
            _proposal(
                self.turn.session_id,
                self.turn.turn_id,
                proposal_id="proposal-2",
                action_name="files.open",
                arguments={"path": "result 1"},
            )
        )

        assert out_of_range.request is not None
        assert expired.request is not None
        self.assertEqual(out_of_range.request.parameters, {"path": "result 2"})
        self.assertEqual(expired.request.parameters, {"path": "result 1"})

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


def _file_match(name: str) -> FileSearchMatch:
    return FileSearchMatch(
        name=name,
        path=rf"C:\Users\Private\Downloads\{name}",
        size_bytes=1024,
        modified_at="2026-08-12T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
