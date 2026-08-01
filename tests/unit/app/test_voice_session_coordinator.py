"""Tests for production voice-session lifecycle and concurrent state."""

from __future__ import annotations

import unittest

from project_akiha.app.voice_session_coordinator import (
    InvalidVoiceSessionTransitionError,
    VoiceSessionCoordinator,
)
from project_akiha.core.voice_session import (
    CaptureStage,
    EndpointReason,
    GenerationStage,
    IntentStage,
    PlaybackStage,
    RecognitionStage,
    SessionLifecycle,
    SynthesisStage,
    TranscriptRevision,
    TranscriptStatus,
    TurnInterruptionState,
    VoiceInputMode,
    VoiceProcessingMode,
    VoiceSessionCue,
    VoiceStage,
)


class VoiceSessionCoordinatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator = VoiceSessionCoordinator(
            session_id_factory=lambda: "session-1"
        )

    def test_explicit_startup_and_shutdown_lifecycle(self) -> None:
        starting = self.coordinator.request_start(VoiceProcessingMode.LOCAL_MODULAR)
        active = self.coordinator.activate()
        stopping = self.coordinator.request_stop()
        idle = self.coordinator.finish_stop()

        self.assertEqual(starting.lifecycle, SessionLifecycle.STARTING)
        self.assertEqual(starting.session_id, "session-1")
        self.assertEqual(active.lifecycle, SessionLifecycle.ACTIVE)
        self.assertEqual(stopping.lifecycle, SessionLifecycle.STOPPING)
        self.assertEqual(idle.lifecycle, SessionLifecycle.IDLE)
        self.assertIsNone(idle.session_id)

    def test_invalid_lifecycle_transition_is_rejected(self) -> None:
        with self.assertRaises(InvalidVoiceSessionTransitionError):
            self.coordinator.activate()

    def test_turn_inherits_explicit_session_lane(self) -> None:
        self._start(VoiceProcessingMode.HYBRID_API_MODULAR)

        turn = self.coordinator.begin_turn(VoiceInputMode.PUSH_TO_TALK)

        self.assertEqual(turn.processing_mode, VoiceProcessingMode.HYBRID_API_MODULAR)
        self.assertEqual(turn.session_id, "session-1")

    def test_capture_and_recognition_can_overlap(self) -> None:
        turn = self._start_turn()

        self._transition(turn, VoiceStage.CAPTURE, CaptureStage.CAPTURING)
        self._transition(turn, VoiceStage.RECOGNITION, RecognitionStage.PARTIAL)

        current = self.coordinator.snapshot.active_turn
        assert current is not None
        self.assertEqual(current.stages.capture, CaptureStage.CAPTURING)
        self.assertEqual(current.stages.recognition, RecognitionStage.PARTIAL)
        self.assertEqual(
            self.coordinator.snapshot.dominant_cue, VoiceSessionCue.LISTENING
        )

    def test_generation_synthesis_and_playback_can_overlap(self) -> None:
        turn = self._start_turn()

        self._transition(turn, VoiceStage.GENERATION, GenerationStage.STREAMING)
        self._transition(turn, VoiceStage.SYNTHESIS, SynthesisStage.QUEUED)
        self._transition(turn, VoiceStage.PLAYBACK, PlaybackStage.BUFFERING)

        current = self.coordinator.snapshot.active_turn
        assert current is not None
        self.assertEqual(current.stages.generation, GenerationStage.STREAMING)
        self.assertEqual(current.stages.synthesis, SynthesisStage.QUEUED)
        self.assertEqual(current.stages.playback, PlaybackStage.BUFFERING)
        self.assertEqual(
            self.coordinator.snapshot.dominant_cue, VoiceSessionCue.SPEAKING
        )

    def test_wrong_stage_enum_is_rejected(self) -> None:
        turn = self._start_turn()

        with self.assertRaisesRegex(TypeError, "CaptureStage"):
            self._transition(turn, VoiceStage.CAPTURE, RecognitionStage.PARTIAL)

    def test_illegal_stage_transition_is_rejected(self) -> None:
        turn = self._start_turn()

        with self.assertRaises(InvalidVoiceSessionTransitionError):
            self._transition(turn, VoiceStage.CAPTURE, CaptureStage.COMPLETE)

    def test_speculative_intent_cannot_commit_before_final_transcript(self) -> None:
        turn = self._start_turn()
        self._transition(turn, VoiceStage.INTENT, IntentStage.SPECULATIVE)

        with self.assertRaisesRegex(
            InvalidVoiceSessionTransitionError,
            "final transcript",
        ):
            self._transition(turn, VoiceStage.INTENT, IntentStage.COMMITTED)

    def test_final_transcript_allows_intent_commit(self) -> None:
        turn = self._start_turn()
        self.assertTrue(
            self.coordinator.accept_transcript_revision(
                _final_revision(turn.session_id, turn.turn_id)
            )
        )

        self.assertTrue(
            self._transition(turn, VoiceStage.INTENT, IntentStage.COMMITTED)
        )

    def test_replacement_rejects_old_stage_and_transcript_callbacks(self) -> None:
        old_turn = self._start_turn()
        replacement = self.coordinator.replace_turn(VoiceInputMode.PUSH_TO_TALK)

        self.assertFalse(
            self._transition(old_turn, VoiceStage.CAPTURE, CaptureStage.CAPTURING)
        )
        self.assertFalse(
            self.coordinator.accept_transcript_revision(
                _final_revision(old_turn.session_id, old_turn.turn_id)
            )
        )
        self.assertEqual(self.coordinator.snapshot.active_turn, replacement)
        self.assertEqual(
            self.coordinator.snapshot.active_turn.interruption,  # type: ignore[union-attr]
            TurnInterruptionState.NONE,
        )

    def test_cancel_fans_out_to_every_active_cancellable_stage(self) -> None:
        turn = self._start_turn()
        self._transition(turn, VoiceStage.CAPTURE, CaptureStage.CAPTURING)
        self._transition(turn, VoiceStage.RECOGNITION, RecognitionStage.PARTIAL)
        self._transition(turn, VoiceStage.GENERATION, GenerationStage.STREAMING)
        self._transition(turn, VoiceStage.SYNTHESIS, SynthesisStage.ACTIVE)
        self._transition(turn, VoiceStage.PLAYBACK, PlaybackStage.PLAYING)

        cancelled = self.coordinator.cancel_active_turn()

        assert cancelled is not None
        self.assertTrue(cancelled.cancellation_token.is_cancelled)
        self.assertEqual(cancelled.stages.capture, CaptureStage.CANCELLED)
        self.assertEqual(cancelled.stages.recognition, RecognitionStage.CANCELLED)
        self.assertEqual(cancelled.stages.generation, GenerationStage.CANCELLED)
        self.assertEqual(cancelled.stages.synthesis, SynthesisStage.CANCELLED)
        self.assertEqual(cancelled.stages.playback, PlaybackStage.CANCELLED)

    def test_error_cancels_turn_and_requires_cleanup(self) -> None:
        turn = self._start_turn()

        error = self.coordinator.report_error("provider_failed")

        self.assertEqual(error.lifecycle, SessionLifecycle.ERROR)
        self.assertEqual(error.error_code, "provider_failed")
        self.assertEqual(error.dominant_cue, VoiceSessionCue.ERROR)
        self.assertTrue(turn.cancellation_token.is_cancelled)
        self.assertEqual(
            self.coordinator.request_stop().lifecycle,
            SessionLifecycle.STOPPING,
        )

    def test_stop_rejects_late_callbacks_and_close_is_idempotent(self) -> None:
        turn = self._start_turn()
        self.coordinator.request_stop()

        self.assertFalse(
            self.coordinator.accepts_callback(turn.session_id, turn.turn_id)
        )
        self.assertEqual(self.coordinator.close().lifecycle, SessionLifecycle.IDLE)
        self.assertEqual(self.coordinator.close().lifecycle, SessionLifecycle.IDLE)

    def test_observer_receives_immutable_snapshots(self) -> None:
        snapshots = []
        self.coordinator.subscribe(snapshots.append)

        self._start()
        self.coordinator.begin_turn(VoiceInputMode.PUSH_TO_TALK)

        self.assertEqual(
            [snapshot.lifecycle for snapshot in snapshots[:2]],
            [SessionLifecycle.STARTING, SessionLifecycle.ACTIVE],
        )
        self.assertIsNotNone(snapshots[-1].active_turn)

    def _start(
        self,
        mode: VoiceProcessingMode = VoiceProcessingMode.LOCAL_MODULAR,
    ) -> None:
        self.coordinator.request_start(mode)
        self.coordinator.activate()

    def _start_turn(self):
        self._start()
        return self.coordinator.begin_turn(VoiceInputMode.PUSH_TO_TALK)

    def _transition(self, turn, stage: VoiceStage, next_state) -> bool:
        return self.coordinator.transition_stage(
            turn.session_id,
            turn.turn_id,
            stage,
            next_state,
        )


def _final_revision(session_id: str, turn_id: str) -> TranscriptRevision:
    return TranscriptRevision(
        session_id=session_id,
        turn_id=turn_id,
        revision_number=1,
        text="Open Discord",
        status=TranscriptStatus.FINAL,
        provider_name="fake",
        endpoint_reason=EndpointReason.SILENCE,
    )


if __name__ == "__main__":
    unittest.main()
