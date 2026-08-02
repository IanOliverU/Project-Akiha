"""Bounded rolling recognition over the existing faster-whisper service."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from project_akiha.core.voice_session import (
    AudioFrame,
    EndpointReason,
    RollingAudioBuffer,
    TranscriptConfidence,
    TranscriptRevision,
    TranscriptStatus,
    VoiceCancellationToken,
)
from project_akiha.providers.voice import CapturedAudio, VoiceTranscript
from project_akiha.services.speech_input import (
    SpeechInputService,
    SpeechInputServiceError,
)
from project_akiha.services.transcript_stabilization import (
    PartialTranscriptStabilizer,
)
from project_akiha.services.voice_confidence import voice_confidence_level


@dataclass(frozen=True, slots=True)
class RollingRecognitionHypothesis:
    """One bounded-window result awaiting transcript-revision stabilization."""

    session_id: str
    turn_id: str
    first_frame_sequence: int
    last_frame_sequence: int
    transcript: VoiceTranscript
    is_final: bool = False
    endpoint_reason: EndpointReason | None = None

    def __post_init__(self) -> None:
        if self.is_final and self.endpoint_reason is None:
            raise ValueError(
                "Final recognition hypothesis requires an endpoint reason."
            )
        if not self.is_final and self.endpoint_reason is not None:
            raise ValueError(
                "Partial recognition hypothesis cannot have an endpoint reason."
            )


class RollingFasterWhisperAdapter:
    """Request overlapping bounded STT windows without owning a microphone."""

    def __init__(
        self,
        service: SpeechInputService,
        *,
        partial_interval_seconds: float = 0.6,
        partial_window_seconds: float = 8.0,
        maximum_utterance_seconds: float = 30.0,
    ) -> None:
        if partial_interval_seconds <= 0:
            raise ValueError("Partial recognition interval must be positive.")
        if partial_window_seconds <= 0:
            raise ValueError("Partial recognition window must be positive.")
        if maximum_utterance_seconds <= 0:
            raise ValueError("Maximum utterance duration must be positive.")
        if partial_interval_seconds > partial_window_seconds:
            raise ValueError("Partial interval cannot exceed its recognition window.")
        if partial_window_seconds > maximum_utterance_seconds:
            raise ValueError("Partial window cannot exceed the utterance limit.")

        self._service = service
        self._partial_interval_seconds = partial_interval_seconds
        self._partial_window_seconds = partial_window_seconds
        self._buffer = RollingAudioBuffer(
            maximum_duration_seconds=maximum_utterance_seconds
        )
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._language: str | None = None
        self._cancellation_token: VoiceCancellationToken | None = None
        self._bytes_since_partial = 0
        self._partial_interval_bytes = 0

    @property
    def is_active(self) -> bool:
        return self._session_id is not None

    def start_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        cancellation_token: VoiceCancellationToken,
        language: str | None = None,
    ) -> None:
        """Claim one turn; its PCM format arrives with frame zero."""
        if self.is_active:
            raise RuntimeError("Rolling faster-whisper adapter already owns a turn.")
        if cancellation_token.is_cancelled:
            raise asyncio.CancelledError
        if not session_id.strip() or not turn_id.strip():
            raise ValueError("Rolling recognition IDs cannot be blank.")
        self._session_id = session_id
        self._turn_id = turn_id
        self._language = language
        self._cancellation_token = cancellation_token
        self._bytes_since_partial = 0
        self._partial_interval_bytes = 0

    async def accept_audio(
        self,
        frame: AudioFrame,
    ) -> RollingRecognitionHypothesis | None:
        """Accept one frame and occasionally transcribe the recent rolling window."""
        self.buffer_audio(frame)
        if self._bytes_since_partial < self._partial_interval_bytes:
            return None
        self._bytes_since_partial %= self._partial_interval_bytes

        snapshot = self._buffer.snapshot(
            maximum_duration_seconds=self._partial_window_seconds
        )
        assert snapshot is not None
        try:
            transcript = await self._service.transcribe(
                self._captured_audio(snapshot.data, frame)
            )
        except SpeechInputServiceError as error:
            if error.code == "empty_transcript":
                return None
            raise
        self._raise_if_cancelled()
        return RollingRecognitionHypothesis(
            session_id=snapshot.session_id,
            turn_id=snapshot.turn_id,
            first_frame_sequence=snapshot.first_sequence_number,
            last_frame_sequence=snapshot.last_sequence_number,
            transcript=transcript,
        )

    def buffer_audio(self, frame: AudioFrame) -> None:
        """Retain one frame without spending inference on a partial result."""
        self._require_active()
        self._raise_if_cancelled()
        if not self._buffer.is_active:
            self._start_buffer(frame)
        self._buffer.accept(frame)
        self._bytes_since_partial += len(frame.data)

    async def finalize(
        self,
        endpoint_reason: EndpointReason,
    ) -> RollingRecognitionHypothesis:
        """Transcribe the bounded utterance once and release temporary PCM."""
        self._require_active()
        self._raise_if_cancelled()
        snapshot = self._buffer.snapshot()
        if snapshot is None:
            self.cancel()
            raise ValueError("Rolling recognition received no audio.")
        try:
            transcript = await self._service.transcribe(
                CapturedAudio(
                    data=snapshot.data,
                    sample_rate_hz=snapshot.sample_rate_hz,
                    channels=snapshot.channels,
                    sample_width_bytes=snapshot.sample_width_bytes,
                    language=self._language,
                )
            )
            self._raise_if_cancelled()
            return RollingRecognitionHypothesis(
                session_id=snapshot.session_id,
                turn_id=snapshot.turn_id,
                first_frame_sequence=snapshot.first_sequence_number,
                last_frame_sequence=snapshot.last_sequence_number,
                transcript=transcript,
                is_final=True,
                endpoint_reason=endpoint_reason,
            )
        finally:
            self._release()

    def cancel(self) -> None:
        """Discard temporary PCM and reject any eventual provider result."""
        token = self._cancellation_token
        if token is not None:
            token.cancel()
        self._release()

    def _start_buffer(self, frame: AudioFrame) -> None:
        assert self._session_id is not None
        assert self._turn_id is not None
        if (frame.session_id, frame.turn_id) != (
            self._session_id,
            self._turn_id,
        ):
            raise ValueError("Audio frame belongs to a different recognition turn.")
        self._buffer.start_turn(
            session_id=self._session_id,
            turn_id=self._turn_id,
            sample_rate_hz=frame.sample_rate_hz,
            channels=frame.channels,
            sample_width_bytes=frame.sample_width_bytes,
        )
        interval_bytes = int(
            frame.sample_rate_hz
            * frame.sample_stride_bytes
            * self._partial_interval_seconds
        )
        interval_bytes -= interval_bytes % frame.sample_stride_bytes
        self._partial_interval_bytes = max(frame.sample_stride_bytes, interval_bytes)

    def _captured_audio(self, data: bytes, frame: AudioFrame) -> CapturedAudio:
        return CapturedAudio(
            data=data,
            sample_rate_hz=frame.sample_rate_hz,
            channels=frame.channels,
            sample_width_bytes=frame.sample_width_bytes,
            language=self._language,
        )

    def _require_active(self) -> None:
        if self._session_id is None or self._turn_id is None:
            raise RuntimeError("Rolling faster-whisper adapter does not own a turn.")

    def _raise_if_cancelled(self) -> None:
        token = self._cancellation_token
        if token is None or token.is_cancelled:
            raise asyncio.CancelledError

    def _release(self) -> None:
        self._buffer.release()
        self._session_id = None
        self._turn_id = None
        self._language = None
        self._cancellation_token = None
        self._bytes_since_partial = 0
        self._partial_interval_bytes = 0


class RollingFasterWhisperRecognizer:
    """Emit ordered canonical revisions over the bounded rolling adapter."""

    def __init__(
        self,
        adapter: RollingFasterWhisperAdapter,
        *,
        provider_name: str = "faster-whisper",
        language: str | None = None,
    ) -> None:
        if not provider_name.strip():
            raise ValueError("Rolling recognizer provider name cannot be blank.")
        self._adapter = adapter
        self._provider_name = provider_name.strip()
        self._language = language
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._on_revision: Callable[[TranscriptRevision], None] | None = None
        self._next_revision_number = 0
        self._final_emitted = False
        self._stabilizer = PartialTranscriptStabilizer()

    @property
    def is_active(self) -> bool:
        return self._session_id is not None and not self._final_emitted

    def start_turn(
        self,
        session_id: str,
        turn_id: str,
        on_revision: Callable[[TranscriptRevision], None],
        cancellation_token: VoiceCancellationToken,
    ) -> None:
        """Start one revision stream owned by the supplied session and turn."""
        if self.is_active:
            raise RuntimeError("Rolling recognizer already owns an active turn.")
        self._adapter.start_turn(
            session_id=session_id,
            turn_id=turn_id,
            cancellation_token=cancellation_token,
            language=self._language,
        )
        self._session_id = session_id
        self._turn_id = turn_id
        self._on_revision = on_revision
        self._next_revision_number = 0
        self._final_emitted = False
        self._stabilizer.reset()

    async def accept_audio(self, frame: AudioFrame) -> None:
        """Process one frame and emit a stable replaceable partial when available."""
        if not self.is_active:
            raise RuntimeError("Rolling recognizer does not own an active turn.")
        hypothesis = await self._adapter.accept_audio(frame)
        if hypothesis is None:
            return
        text = self._stabilizer.observe(hypothesis.transcript.text)
        if text is None:
            return
        self._emit(self._revision(hypothesis, text, TranscriptStatus.PARTIAL))

    def buffer_audio(self, frame: AudioFrame) -> None:
        """Retain final queued audio without producing another partial."""
        if not self.is_active:
            raise RuntimeError("Rolling recognizer does not own an active turn.")
        self._adapter.buffer_audio(frame)

    async def finalize(self, endpoint_reason: EndpointReason) -> None:
        """Emit exactly one authoritative final revision for this turn."""
        if not self.is_active:
            raise RuntimeError("Rolling recognizer does not own an active turn.")
        hypothesis = await self._adapter.finalize(endpoint_reason)
        if self._final_emitted:
            return
        self._final_emitted = True
        self._emit(
            self._revision(
                hypothesis,
                " ".join(hypothesis.transcript.text.split()),
                TranscriptStatus.FINAL,
            )
        )

    def cancel(self) -> None:
        """Cancel recognition and release the revision callback."""
        self._adapter.cancel()
        self._release()

    def _revision(
        self,
        hypothesis: RollingRecognitionHypothesis,
        text: str,
        status: TranscriptStatus,
    ) -> TranscriptRevision:
        confidence = _CONFIDENCE_BANDS.get(
            voice_confidence_level(hypothesis.transcript.confidence),
            TranscriptConfidence.UNKNOWN,
        )
        return TranscriptRevision(
            session_id=hypothesis.session_id,
            turn_id=hypothesis.turn_id,
            revision_number=self._next_revision_number,
            text=text,
            status=status,
            provider_name=self._provider_name,
            detected_language=hypothesis.transcript.detected_language,
            confidence=confidence,
            endpoint_reason=(
                hypothesis.endpoint_reason if status is TranscriptStatus.FINAL else None
            ),
        )

    def _emit(self, revision: TranscriptRevision) -> None:
        if (revision.session_id, revision.turn_id) != (
            self._session_id,
            self._turn_id,
        ):
            return
        callback = self._on_revision
        if callback is None:
            return
        callback(revision)
        self._next_revision_number += 1

    def _release(self) -> None:
        self._session_id = None
        self._turn_id = None
        self._on_revision = None
        self._next_revision_number = 0
        self._final_emitted = False
        self._stabilizer.reset()


_CONFIDENCE_BANDS = {
    "low": TranscriptConfidence.LOW,
    "medium": TranscriptConfidence.MEDIUM,
    "high": TranscriptConfidence.HIGH,
}
