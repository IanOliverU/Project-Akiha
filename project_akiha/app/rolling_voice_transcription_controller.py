"""Route cumulative Qt capture through bounded rolling speech recognition."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.app.voice_audio_bridge import CumulativeAudioFrameBridge
from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import VoiceSessionCoordinator
from project_akiha.app.voice_transcription_controller import (
    VoiceTranscriptionController,
)
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.voice_session import (
    AudioFrame,
    EndpointReason,
    TranscriptConfidence,
    TranscriptRevision,
    TranscriptStatus,
)
from project_akiha.providers.voice import CapturedAudio
from project_akiha.services.rolling_speech_input import (
    RollingFasterWhisperAdapter,
    RollingFasterWhisperRecognizer,
)
from project_akiha.services.speech_input import SpeechInputService
from project_akiha.ui.rolling_voice_recognition_worker import (
    RollingVoiceRecognitionThread,
    VoiceTranscriptRevisionRelay,
)

_DIAGNOSTIC_SOURCE = "settings_microphone_test"


class _RollingThread(Protocol):
    recognition_failed: object
    recognition_cancelled: object
    finished: object
    is_finalizing: bool

    def start(self) -> None:
        """Start recognition."""

    def cancel(self) -> None:
        """Request cancellation."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion."""


class _RevisionSignal(Protocol):
    def connect(self, handler: Callable[[object], None]) -> None:
        """Connect one queued revision handler."""

    def emit(self, revision: object) -> None:
        """Emit one revision."""


class _RevisionRelay(Protocol):
    revision_ready: _RevisionSignal


class RollingVoiceTranscriptionController:
    """Own one rolling recognizer while preserving existing voice events."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        session_coordinator: VoiceSessionCoordinator,
        service: SpeechInputService,
        config: VoiceConfig,
        *,
        diagnostic_controller: VoiceTranscriptionController | None = None,
        thread_factory: Callable[
            [
                RollingFasterWhisperRecognizer,
                tuple[AudioFrame, ...],
                EndpointReason | None,
            ],
            _RollingThread,
        ] = RollingVoiceRecognitionThread,
        relay_factory: Callable[[], _RevisionRelay] = VoiceTranscriptRevisionRelay,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._session_coordinator = session_coordinator
        self._service = service
        self._config = config
        self._diagnostic_controller = (
            diagnostic_controller
            or VoiceTranscriptionController(
                event_bus,
                voice_controller,
                service,
            )
        )
        self._thread_factory = thread_factory
        self._relay = relay_factory()
        self._relay.revision_ready.connect(self._handle_revision)
        self._bridge: CumulativeAudioFrameBridge | None = None
        self._recognizer: RollingFasterWhisperRecognizer | None = None
        self._active_thread: _RollingThread | None = None
        self._pending_frames: list[AudioFrame] = []
        self._pending_endpoint: EndpointReason | None = None
        self._endpoint_reason = EndpointReason.MANUAL_STOP

        event_bus.subscribe(EventType.VOICE_LISTEN_REQUESTED, self._handle_listen)
        event_bus.subscribe(EventType.VOICE_LISTEN_STOP_REQUESTED, self._handle_stop)
        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_cancel,
        )

    def apply_service(
        self,
        service: SpeechInputService,
        config: VoiceConfig | None = None,
    ) -> None:
        """Use an updated provider and recognition settings on the next turn."""
        self._service = service
        if config is not None:
            self._config = config
        self._diagnostic_controller.apply_service(service)

    def submit_partial(self, audio: CapturedAudio) -> None:
        """Queue newly appended bounded frames from a cumulative live snapshot."""
        frames = self._frames_from_snapshot(audio)
        if frames:
            self._enqueue(frames)

    def submit(self, audio: CapturedAudio) -> None:
        """Queue final appended frames and one authoritative finalization."""
        frames = self._frames_from_snapshot(audio)
        bridge = self._bridge
        if bridge is not None:
            bridge.release()
            self._bridge = None
        self._enqueue(frames, endpoint_reason=self._endpoint_reason)

    def submit_test(self, audio: CapturedAudio) -> None:
        """Keep Settings microphone diagnostics on the proven batch path."""
        self._diagnostic_controller.submit_test(audio)

    def cancel(self, wait_ms: int = 2_000) -> None:
        """Cancel rolling and diagnostic recognition during shutdown."""
        unfinished = 0
        thread = self._active_thread
        self._active_thread = None
        if thread is not None:
            thread.cancel()
            if wait_ms > 0 and not thread.wait(wait_ms):
                unfinished += 1
        self._release_turn(cancel_recognizer=True)
        self._diagnostic_controller.cancel(wait_ms=wait_ms)
        if unfinished:
            raise RuntimeError("Rolling voice transcription worker did not stop.")

    def _handle_listen(self, event: Event) -> None:
        if event.payload.get("source") == _DIAGNOSTIC_SOURCE:
            return
        turn = self._session_coordinator.snapshot.active_turn
        if turn is None:
            return
        self._release_turn(cancel_recognizer=True)
        bridge = CumulativeAudioFrameBridge()
        bridge.start_turn(session_id=turn.session_id, turn_id=turn.turn_id)
        recognizer = RollingFasterWhisperRecognizer(
            RollingFasterWhisperAdapter(
                self._service,
                maximum_utterance_seconds=float(self._config.capture_timeout_seconds),
            ),
            provider_name=self._config.input_provider,
            language=self._config.input_language,
        )
        recognizer.start_turn(
            turn.session_id,
            turn.turn_id,
            self._relay.revision_ready.emit,
            turn.cancellation_token,
        )
        self._bridge = bridge
        self._recognizer = recognizer
        self._endpoint_reason = EndpointReason.MANUAL_STOP

    def _handle_stop(self, event: Event) -> None:
        if event.payload.get("source") == _DIAGNOSTIC_SOURCE:
            return
        self._endpoint_reason = _endpoint_reason(event.payload.get("reason"))

    def _handle_cancel(self, event: Event) -> None:
        del event
        self.cancel(wait_ms=0)

    def _frames_from_snapshot(
        self,
        audio: CapturedAudio,
    ) -> tuple[AudioFrame, ...]:
        bridge = self._bridge
        if bridge is None:
            return ()
        try:
            return bridge.accept_snapshot(audio)
        except (RuntimeError, ValueError) as error:
            self._voice_controller.report_error(
                "audio_frame_bridge_failed",
                f"Microphone audio framing failed: {error}",
            )
            self._release_turn(cancel_recognizer=True)
            return ()

    def _enqueue(
        self,
        frames: tuple[AudioFrame, ...],
        *,
        endpoint_reason: EndpointReason | None = None,
    ) -> None:
        if self._recognizer is None:
            return
        self._pending_frames.extend(frames)
        if endpoint_reason is not None:
            self._pending_endpoint = endpoint_reason
        if self._active_thread is None:
            self._start_pending()

    def _start_pending(self) -> None:
        recognizer = self._recognizer
        if recognizer is None:
            return
        if not self._pending_frames and self._pending_endpoint is None:
            return
        frames = tuple(self._pending_frames)
        endpoint = self._pending_endpoint
        self._pending_frames.clear()
        self._pending_endpoint = None
        thread = self._thread_factory(recognizer, frames, endpoint)
        thread.recognition_failed.connect(
            lambda code, message, worker=thread: self._handle_failure(
                worker,
                code,
                message,
            )
        )
        thread.recognition_cancelled.connect(
            lambda worker=thread: self._handle_thread_cancelled(worker)
        )
        thread.finished.connect(
            lambda worker=thread: self._handle_thread_finished(worker)
        )
        self._active_thread = thread
        thread.start()

    def _handle_revision(self, value: object) -> None:
        if not isinstance(value, TranscriptRevision):
            return
        if not self._session_coordinator.accepts_callback(
            value.session_id,
            value.turn_id,
        ):
            return
        confidence_level = (
            value.confidence.value
            if value.confidence is not TranscriptConfidence.UNKNOWN
            else None
        )
        if value.status is TranscriptStatus.PARTIAL:
            payload: dict[str, object] = {
                "text": value.text,
                "revision": value,
            }
            if value.detected_language:
                payload["detected_language"] = value.detected_language
            if confidence_level:
                payload["confidence_level"] = confidence_level
            self._event_bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, payload)
            return
        self._voice_controller.publish_transcript(
            value.text,
            value.detected_language,
            confidence_level,
            requires_review=value.confidence is TranscriptConfidence.LOW,
            revision=value,
        )

    def _handle_failure(
        self,
        thread: _RollingThread,
        code: str,
        message: str,
    ) -> None:
        if thread is not self._active_thread:
            return
        if thread.is_finalizing:
            self._voice_controller.report_error(code, message)

    def _handle_thread_cancelled(self, thread: _RollingThread) -> None:
        if thread is self._active_thread:
            self._pending_frames.clear()
            self._pending_endpoint = None

    def _handle_thread_finished(self, thread: _RollingThread) -> None:
        if thread is not self._active_thread:
            return
        was_finalizing = thread.is_finalizing
        self._active_thread = None
        if self._pending_frames or self._pending_endpoint is not None:
            self._start_pending()
        elif was_finalizing:
            self._release_turn(cancel_recognizer=True)

    def _release_turn(self, *, cancel_recognizer: bool) -> None:
        bridge = self._bridge
        self._bridge = None
        if bridge is not None:
            bridge.release()
        recognizer = self._recognizer
        self._recognizer = None
        if cancel_recognizer and recognizer is not None:
            recognizer.cancel()
        self._pending_frames.clear()
        self._pending_endpoint = None


def _endpoint_reason(value: object) -> EndpointReason:
    if value in {"silence_detected", "transcript_inactivity"}:
        return EndpointReason.SILENCE
    return EndpointReason.MANUAL_STOP
