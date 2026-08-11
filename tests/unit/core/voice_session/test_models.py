"""Tests for provider-neutral voice-session contracts."""

from __future__ import annotations

import unittest

from project_akiha.core.voice_session import (
    ActionProposal,
    AudioFrame,
    CanonicalResponseSegment,
    EndpointReason,
    LiveResponseModality,
    LiveSessionCapabilities,
    LiveSessionCapability,
    LiveSessionConfig,
    ModularResponseContext,
    ModularResponseEvent,
    ModularResponseEventKind,
    ResponseSegment,
    SanitizedActionResult,
    TranscriptRevision,
    TranscriptStatus,
    VoiceProcessingMode,
)


class VoiceSessionModelsTest(unittest.TestCase):
    def test_audio_frame_requires_bounded_pcm_metadata(self) -> None:
        frame = AudioFrame(
            session_id="session-1",
            turn_id="1",
            sequence_number=0,
            captured_at_monotonic=1.25,
            sample_rate_hz=16_000,
            channels=1,
            sample_width_bytes=2,
            data=b"\x00\x01",
        )

        self.assertEqual(frame.sequence_number, 0)
        self.assertNotIn("\\x00", repr(frame))

    def test_audio_frame_rejects_oversized_payload(self) -> None:
        with self.assertRaisesRegex(ValueError, "one MiB"):
            AudioFrame(
                session_id="session-1",
                turn_id="1",
                sequence_number=0,
                captured_at_monotonic=1.25,
                sample_rate_hz=16_000,
                channels=1,
                sample_width_bytes=2,
                data=b"0" * 1_048_577,
            )

    def test_final_transcript_requires_endpoint_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "endpoint reason"):
            TranscriptRevision(
                session_id="session-1",
                turn_id="1",
                revision_number=1,
                text="Open Discord",
                status=TranscriptStatus.FINAL,
                provider_name="faster-whisper",
            )

    def test_live_config_requires_hosted_mode_and_bounded_duration(self) -> None:
        with self.assertRaisesRegex(ValueError, "hosted-live"):
            LiveSessionConfig(
                session_id="session-1",
                processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
                provider_name="gemini",
                input_sample_rate_hz=16_000,
                max_duration_seconds=600,
            )
        with self.assertRaisesRegex(ValueError, "between 1 and 900"):
            LiveSessionConfig(
                session_id="session-1",
                processing_mode=VoiceProcessingMode.HOSTED_LIVE,
                provider_name="gemini",
                input_sample_rate_hz=16_000,
                max_duration_seconds=901,
            )

    def test_live_capabilities_are_explicit_and_immutable(self) -> None:
        capabilities = LiveSessionCapabilities(
            provider_name="gemini",
            capabilities=frozenset(
                {
                    LiveSessionCapability.AUDIO_INPUT,
                    LiveSessionCapability.AUDIO_OUTPUT,
                }
            ),
            input_sample_rate_hz=16_000,
            output_sample_rate_hz=24_000,
        )

        self.assertTrue(capabilities.supports(LiveSessionCapability.AUDIO_INPUT))
        self.assertFalse(capabilities.supports(LiveSessionCapability.TOOL_PROPOSALS))
        self.assertEqual(LiveResponseModality.AUDIO, "audio")

    def test_partial_transcript_cannot_claim_endpoint_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "partial transcript"):
            TranscriptRevision(
                session_id="session-1",
                turn_id="1",
                revision_number=1,
                text="Open",
                status=TranscriptStatus.PARTIAL,
                provider_name="faster-whisper",
                endpoint_reason=EndpointReason.SILENCE,
            )

    def test_action_proposal_copies_arguments_into_read_only_mapping(self) -> None:
        arguments = {"application_id": "discord"}
        proposal = ActionProposal(
            session_id="session-1",
            turn_id="1",
            proposal_id="proposal-1",
            source="local.intent",
            action_name="applications.launch",
            arguments=arguments,
        )
        arguments["application_id"] = "chrome"

        self.assertEqual(proposal.arguments["application_id"], "discord")
        with self.assertRaises(TypeError):
            proposal.arguments["application_id"] = "spotify"  # type: ignore[index]

    def test_action_proposal_rejects_nested_unbounded_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "primitive bounded values"):
            ActionProposal(
                session_id="session-1",
                turn_id="1",
                proposal_id="proposal-1",
                source="local.intent",
                action_name="applications.launch",
                arguments={"nested": {"command": "unrestricted"}},
            )

    def test_action_proposal_requires_session_ownership(self) -> None:
        with self.assertRaisesRegex(ValueError, "session ID"):
            ActionProposal(
                session_id="",
                turn_id="1",
                proposal_id="proposal-1",
                source="gemini.live",
                action_name="applications.launch",
                arguments={"application_id": "discord"},
            )

    def test_sanitized_action_result_requires_session_ownership(self) -> None:
        with self.assertRaisesRegex(ValueError, "session ID"):
            SanitizedActionResult(
                session_id="",
                turn_id="1",
                proposal_id="proposal-1",
                status="success",
                message="Completed.",
            )

    def test_modular_response_context_requires_paired_turn_identity(self) -> None:
        with self.assertRaisesRegex(ValueError, "provided together"):
            ModularResponseContext(
                response_id="response-1",
                processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
                session_id="session-1",
            )

    def test_hosted_live_cannot_enter_modular_response_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "LiveSessionAdapter"):
            ModularResponseContext(
                response_id="response-1",
                processing_mode=VoiceProcessingMode.HOSTED_LIVE,
            )

    def test_response_event_hides_canonical_text_from_repr(self) -> None:
        event = ModularResponseEvent(
            context=ModularResponseContext(
                response_id="response-1",
                processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
            ),
            kind=ModularResponseEventKind.DELTA,
            sequence_number=1,
            text="Private provider response",
        )

        self.assertNotIn("Private provider response", repr(event))

    def test_started_response_event_requires_sequence_zero(self) -> None:
        context = ModularResponseContext(
            response_id="response-1",
            processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
        )

        with self.assertRaisesRegex(ValueError, "sequence zero"):
            ModularResponseEvent(
                context=context,
                kind=ModularResponseEventKind.STARTED,
                sequence_number=1,
            )

    def test_canonical_response_segment_hides_text_from_repr(self) -> None:
        segment = CanonicalResponseSegment(
            response_id="response-1",
            segment_index=0,
            canonical_text="Private assistant response.",
            is_final=True,
        )

        self.assertNotIn("Private assistant response", repr(segment))

    def test_response_segment_preserves_canonical_and_hides_both_texts(self) -> None:
        segment = ResponseSegment(
            response_id="response-1",
            segment_index=0,
            canonical_text="**Canonical response.**",
            speech_text="Canonical response.",
            speaking_rate_multiplier=0.94,
            is_final=True,
        )

        self.assertEqual(segment.canonical_text, "**Canonical response.**")
        self.assertEqual(segment.speech_text, "Canonical response.")
        self.assertNotIn("Canonical response", repr(segment))


if __name__ == "__main__":
    unittest.main()
