"""Route the existing push-to-talk event path through voice sessions."""

from __future__ import annotations

from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import (
    InvalidVoiceSessionTransitionError,
    VoiceSessionCoordinator,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import (
    CaptureStage,
    EndpointReason,
    RecognitionStage,
    SessionLifecycle,
    TranscriptConfidence,
    TranscriptRevision,
    TranscriptStatus,
    VoiceInputMode,
    VoiceProcessingMode,
    VoiceStage,
)

_DIAGNOSTIC_SOURCE = "settings_microphone_test"
_HOSTED_LIVE_SOURCE = "hosted_live"
_CONFIDENCE_VALUES = {
    confidence.value: confidence for confidence in TranscriptConfidence
}
_NON_FATAL_SESSION_ERRORS = {
    "half_duplex_input_active",
    "half_duplex_output_active",
}


class PushToTalkSessionController:
    """Translate legacy voice events into one bounded coordinator session."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        session_coordinator: VoiceSessionCoordinator,
        *,
        processing_mode_provider: Callable[[], VoiceProcessingMode],
        input_provider_name: Callable[[], str],
    ) -> None:
        self._voice_controller = voice_controller
        self._coordinator = session_coordinator
        self._processing_mode_provider = processing_mode_provider
        self._input_provider_name = input_provider_name
        self._owns_recording = False
        self._persistent_session = False
        self._next_revision = 0
        self._endpoint_reason = EndpointReason.MANUAL_STOP

        event_bus.subscribe(
            EventType.VOICE_LISTEN_REQUESTED,
            self._handle_listen_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            self._handle_listen_stop_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_listen_cancel_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_TRANSCRIPT_PARTIAL,
            self._handle_transcript_partial,
        )
        event_bus.subscribe(
            EventType.VOICE_TRANSCRIPT_READY,
            self._handle_transcript_ready,
        )
        event_bus.subscribe(
            EventType.VOICE_ERROR_OCCURRED,
            self._handle_voice_error,
        )

    @property
    def coordinator(self) -> VoiceSessionCoordinator:
        """Expose the shared coordinator to worker adapters and diagnostics."""
        return self._coordinator

    def close(self) -> None:
        """Reject callbacks before runtime workers begin shutdown."""
        self._owns_recording = False
        self._persistent_session = False
        self._coordinator.close()

    def _handle_listen_requested(self, event: Event) -> None:
        source = event.payload.get("source")
        if source in {_DIAGNOSTIC_SOURCE, _HOSTED_LIVE_SOURCE}:
            return
        if (
            self._voice_controller.state is not VoiceState.LISTENING
            or self._voice_controller.operation != "input"
        ):
            return

        snapshot = self._coordinator.snapshot
        persistent_session = (
            snapshot.lifecycle is SessionLifecycle.ACTIVE
            and snapshot.active_turn is None
        )
        try:
            if persistent_session:
                turn = self._coordinator.begin_turn(VoiceInputMode.LOCAL_CONVERSATION)
            else:
                self._coordinator.close()
                self._coordinator.request_start(self._processing_mode_provider())
                self._coordinator.activate()
                turn = self._coordinator.begin_turn(VoiceInputMode.PUSH_TO_TALK)
            self._coordinator.transition_stage(
                turn.session_id,
                turn.turn_id,
                VoiceStage.CAPTURE,
                CaptureStage.CAPTURING,
            )
        except (RuntimeError, TypeError, ValueError) as error:
            self._owns_recording = False
            self._coordinator.close()
            self._voice_controller.report_error(
                "voice_session_start_failed",
                f"Voice session could not start: {error}",
            )
            return

        self._owns_recording = True
        self._persistent_session = persistent_session
        self._next_revision = 0
        self._endpoint_reason = EndpointReason.MANUAL_STOP

    def _handle_listen_stop_requested(self, event: Event) -> None:
        turn = self._active_turn()
        if turn is None:
            return
        self._endpoint_reason = _endpoint_reason(event.payload.get("reason"))
        try:
            if turn.stages.capture is CaptureStage.CAPTURING:
                self._coordinator.transition_stage(
                    turn.session_id,
                    turn.turn_id,
                    VoiceStage.CAPTURE,
                    CaptureStage.ENDPOINTING,
                )
                turn = self._active_turn()
                assert turn is not None
            if turn.stages.capture is CaptureStage.ENDPOINTING:
                self._coordinator.transition_stage(
                    turn.session_id,
                    turn.turn_id,
                    VoiceStage.CAPTURE,
                    CaptureStage.COMPLETE,
                )
                turn = self._active_turn()
                assert turn is not None
            if turn.stages.recognition in {
                RecognitionStage.IDLE,
                RecognitionStage.PARTIAL,
            }:
                self._coordinator.transition_stage(
                    turn.session_id,
                    turn.turn_id,
                    VoiceStage.RECOGNITION,
                    RecognitionStage.FINALIZING,
                )
        except InvalidVoiceSessionTransitionError as error:
            self._voice_controller.report_error(
                "voice_session_transition_failed",
                str(error),
            )

    def _handle_listen_cancel_requested(self, event: Event) -> None:
        del event
        if not self._owns_recording:
            return
        persistent_session = self._persistent_session
        self._owns_recording = False
        self._persistent_session = False
        self._coordinator.cancel_active_turn()
        if not persistent_session:
            self._coordinator.close()

    def _handle_transcript_partial(self, event: Event) -> None:
        turn = self._active_turn()
        if turn is None or turn.stages.recognition is RecognitionStage.FINALIZING:
            return
        revision = self._build_revision(event, TranscriptStatus.PARTIAL)
        if revision is not None and self._coordinator.accept_transcript_revision(
            revision
        ):
            self._next_revision += 1

    def _handle_transcript_ready(self, event: Event) -> None:
        turn = self._active_turn()
        if turn is None:
            return
        revision = self._build_revision(event, TranscriptStatus.FINAL)
        if revision is None:
            return
        if not self._coordinator.accept_transcript_revision(revision):
            return

        self._next_revision += 1
        self._coordinator.complete_turn(turn.session_id, turn.turn_id)
        self._owns_recording = False
        persistent_session = self._persistent_session
        self._persistent_session = False
        if not persistent_session:
            self._coordinator.close()

    def _handle_voice_error(self, event: Event) -> None:
        if not self._owns_recording:
            return
        code = event.payload.get("code")
        safe_code = code if isinstance(code, str) else "voice_session_error"
        if safe_code in _NON_FATAL_SESSION_ERRORS:
            return
        if self._coordinator.snapshot.lifecycle in {
            SessionLifecycle.STARTING,
            SessionLifecycle.ACTIVE,
        }:
            self._coordinator.report_error(safe_code)
        self.close()

    def _active_turn(self):
        if not self._owns_recording:
            return None
        snapshot = self._coordinator.snapshot
        if snapshot.lifecycle is not SessionLifecycle.ACTIVE:
            return None
        return snapshot.active_turn

    def _build_revision(
        self,
        event: Event,
        status: TranscriptStatus,
    ) -> TranscriptRevision | None:
        turn = self._active_turn()
        provided_revision = event.payload.get("revision")
        if isinstance(provided_revision, TranscriptRevision):
            if (
                turn is not None
                and provided_revision.status is status
                and (provided_revision.session_id, provided_revision.turn_id)
                == (turn.session_id, turn.turn_id)
            ):
                return provided_revision
            return None
        text = event.payload.get("text")
        if turn is None or not isinstance(text, str) or not text.strip():
            return None
        language = event.payload.get("detected_language")
        confidence = event.payload.get("confidence_level")
        return TranscriptRevision(
            session_id=turn.session_id,
            turn_id=turn.turn_id,
            revision_number=self._next_revision,
            text=text.strip(),
            status=status,
            provider_name=self._input_provider_name().strip() or "unknown",
            detected_language=(
                language.strip()
                if isinstance(language, str) and language.strip()
                else None
            ),
            confidence=(
                _CONFIDENCE_VALUES.get(confidence, TranscriptConfidence.UNKNOWN)
                if isinstance(confidence, str)
                else TranscriptConfidence.UNKNOWN
            ),
            endpoint_reason=(
                self._endpoint_reason if status is TranscriptStatus.FINAL else None
            ),
        )


def _endpoint_reason(value: object) -> EndpointReason:
    if value in {"silence_detected", "transcript_inactivity"}:
        return EndpointReason.SILENCE
    return EndpointReason.MANUAL_STOP
