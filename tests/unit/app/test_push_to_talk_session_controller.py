"""Tests for routing existing push-to-talk events through V1 sessions."""

from __future__ import annotations

import unittest

from project_akiha.app.push_to_talk_session_controller import (
    PushToTalkSessionController,
)
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.voice_session import (
    CaptureStage,
    EndpointReason,
    RecognitionStage,
    SessionLifecycle,
    TranscriptConfidence,
    VoiceInputMode,
    VoiceProcessingMode,
)


class PushToTalkSessionControllerTest(unittest.TestCase):
    def test_listen_starts_local_push_to_talk_capture(self) -> None:
        bus, _, coordinator, _ = _build()

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        snapshot = coordinator.snapshot
        self.assertEqual(snapshot.lifecycle, SessionLifecycle.ACTIVE)
        self.assertEqual(snapshot.processing_mode, VoiceProcessingMode.LOCAL_MODULAR)
        self.assertEqual(snapshot.active_turn.input_mode, VoiceInputMode.PUSH_TO_TALK)  # type: ignore[union-attr]
        self.assertEqual(
            snapshot.active_turn.stages.capture,  # type: ignore[union-attr]
            CaptureStage.CAPTURING,
        )

    def test_hosted_text_provider_selects_hybrid_modular_lane(self) -> None:
        bus, _, coordinator, _ = _build(
            processing_mode=VoiceProcessingMode.HYBRID_API_MODULAR
        )

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(
            coordinator.snapshot.active_turn.processing_mode,  # type: ignore[union-attr]
            VoiceProcessingMode.HYBRID_API_MODULAR,
        )

    def test_manual_stop_completes_capture_and_finalizes_recognition(self) -> None:
        bus, _, coordinator, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        turn = coordinator.snapshot.active_turn
        assert turn is not None
        self.assertEqual(turn.stages.capture, CaptureStage.COMPLETE)
        self.assertEqual(turn.stages.recognition, RecognitionStage.FINALIZING)

    def test_repeated_stop_is_idempotent_while_final_transcription_runs(self) -> None:
        bus, voice, coordinator, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
        bus.publish(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            {"reason": "transcript_inactivity"},
        )
        voice.publish_transcript("Open Discord", "en", "high")

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)

    def test_partial_and_silence_final_are_recorded_without_changing_events(
        self,
    ) -> None:
        bus, voice, coordinator, _ = _build()
        observed: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_READY, observed.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(
            EventType.VOICE_TRANSCRIPT_PARTIAL,
            {"text": "Open", "detected_language": "en"},
        )
        turn = coordinator.snapshot.active_turn
        assert turn is not None
        self.assertEqual(turn.latest_transcript_revision, 0)
        self.assertIsNone(turn.accepted_final_transcript)

        bus.publish(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            {"reason": "transcript_inactivity"},
        )
        voice.publish_transcript("Open Discord", "en", "high")

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        final_event = next(
            event
            for event in reversed(observed)
            if event.event_type is EventType.VOICE_TRANSCRIPT_READY
        )
        self.assertEqual(final_event.payload["text"], "Open Discord")

        historical = coordinator.snapshot.active_turn
        self.assertIsNone(historical)

    def test_revision_maps_confidence_and_endpoint_reason(self) -> None:
        bus, voice, coordinator, _ = _build()
        revisions = []
        coordinator.subscribe(
            lambda snapshot: revisions.append(
                snapshot.active_turn.accepted_final_transcript
                if snapshot.active_turn is not None
                else None
            )
        )
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            {"reason": "silence_detected"},
        )

        voice.publish_transcript("Open Discord", "en", "low")

        accepted = next(revision for revision in revisions if revision is not None)
        self.assertEqual(accepted.confidence, TranscriptConfidence.LOW)
        self.assertEqual(accepted.endpoint_reason, EndpointReason.SILENCE)

    def test_cancel_closes_session_and_invalidates_turn(self) -> None:
        bus, _, coordinator, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        turn = coordinator.snapshot.active_turn
        assert turn is not None

        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)

        self.assertTrue(turn.cancellation_token.is_cancelled)
        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)
        self.assertFalse(coordinator.accepts_callback(turn.session_id, turn.turn_id))

    def test_persistent_session_keeps_local_conversation_turn_mode(self) -> None:
        bus, _, coordinator, _ = _build()
        coordinator.request_start(VoiceProcessingMode.LOCAL_MODULAR)
        coordinator.activate()

        bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "local_conversation"},
        )

        turn = coordinator.snapshot.active_turn
        assert turn is not None
        self.assertEqual(turn.input_mode, VoiceInputMode.LOCAL_CONVERSATION)
        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.ACTIVE)

    def test_persistent_session_survives_final_transcript_between_turns(self) -> None:
        bus, voice, coordinator, _ = _build()
        coordinator.request_start(VoiceProcessingMode.LOCAL_MODULAR)
        coordinator.activate()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        voice.publish_transcript("Hello Akiha", "en", "high")

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.ACTIVE)
        self.assertIsNone(coordinator.snapshot.active_turn)

    def test_persistent_session_survives_cancelled_microphone_turn(self) -> None:
        bus, _, coordinator, _ = _build()
        coordinator.request_start(VoiceProcessingMode.LOCAL_MODULAR)
        coordinator.activate()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.ACTIVE)
        self.assertIsNone(coordinator.snapshot.active_turn)

    def test_voice_error_closes_owned_session(self) -> None:
        bus, voice, coordinator, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        voice.report_error("capture_failed", "Capture failed.")

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)

    def test_rejected_listen_request_does_not_create_session(self) -> None:
        bus, _, coordinator, _ = _build(config=VoiceConfig())

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)

    def test_microphone_diagnostic_does_not_enter_conversation_ledger(self) -> None:
        bus, _, coordinator, _ = _build()

        bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "settings_microphone_test"},
        )

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)

    def test_shutdown_close_is_idempotent(self) -> None:
        bus, _, coordinator, controller = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.close()
        controller.close()

        self.assertEqual(coordinator.snapshot.lifecycle, SessionLifecycle.IDLE)


def _build(
    *,
    config: VoiceConfig | None = None,
    processing_mode: VoiceProcessingMode = VoiceProcessingMode.LOCAL_MODULAR,
) -> tuple[
    EventBus,
    VoiceController,
    VoiceSessionCoordinator,
    PushToTalkSessionController,
]:
    bus = EventBus()
    voice = VoiceController(bus, config or VoiceConfig(enabled=True))
    coordinator = VoiceSessionCoordinator(session_id_factory=lambda: "session-1")
    controller = PushToTalkSessionController(
        event_bus=bus,
        voice_controller=voice,
        session_coordinator=coordinator,
        processing_mode_provider=lambda: processing_mode,
        input_provider_name=lambda: "faster-whisper",
    )
    return bus, voice, coordinator, controller


if __name__ == "__main__":
    unittest.main()
