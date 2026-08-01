"""Bounded rolling-transcript adapter over the existing STT service."""

from __future__ import annotations

from difflib import SequenceMatcher

from project_akiha.providers.voice import CapturedAudio
from project_akiha.services.speech_input import (
    SpeechInputService,
    SpeechInputServiceError,
)
from spikes.voice_pipeline.pipeline_spike import TranscriptRevision
from spikes.voice_pipeline.qt_audio_bridge import AudioFrame


class RollingTranscriptRecognizer:
    """Emit stabilized partial revisions and one authoritative final."""

    def __init__(
        self,
        service: SpeechInputService,
        *,
        partial_interval_seconds: float = 0.6,
        maximum_utterance_seconds: float = 30.0,
    ) -> None:
        if partial_interval_seconds <= 0:
            raise ValueError("Partial transcript interval must be positive.")
        if maximum_utterance_seconds <= 0:
            raise ValueError("Maximum utterance duration must be positive.")
        if partial_interval_seconds > maximum_utterance_seconds:
            raise ValueError("Partial interval cannot exceed the utterance limit.")
        self._service = service
        self._partial_interval_seconds = partial_interval_seconds
        self._maximum_utterance_seconds = maximum_utterance_seconds
        self._session_id: str | None = None
        self._turn_id: int | None = None
        self._sample_rate_hz = 0
        self._channels = 0
        self._sample_width_bytes = 0
        self._language: str | None = None
        self._buffer = bytearray()
        self._bytes_since_partial = 0
        self._next_frame_sequence = 1
        self._next_revision = 1
        self._stabilizer = _RevisionStabilizer()

    @property
    def is_active(self) -> bool:
        return self._turn_id is not None

    def start(
        self,
        *,
        session_id: str,
        turn_id: int,
        sample_rate_hz: int,
        channels: int,
        sample_width_bytes: int,
        language: str | None = None,
    ) -> None:
        """Start one recognition turn without acquiring microphone hardware."""
        if self.is_active:
            raise RuntimeError("Rolling recognizer already owns a turn.")
        if not session_id.strip():
            raise ValueError("Recognition session ID cannot be empty.")
        if turn_id < 1:
            raise ValueError("Recognition turn ID must be positive.")
        if sample_rate_hz <= 0 or channels <= 0 or sample_width_bytes <= 0:
            raise ValueError("Recognition audio format values must be positive.")
        self._session_id = session_id.strip()
        self._turn_id = turn_id
        self._sample_rate_hz = sample_rate_hz
        self._channels = channels
        self._sample_width_bytes = sample_width_bytes
        self._language = language
        self._buffer.clear()
        self._bytes_since_partial = 0
        self._next_frame_sequence = 1
        self._next_revision = 1
        self._stabilizer.reset()

    async def accept(self, frame: object) -> TranscriptRevision | None:
        """Accept one ordered audio frame and occasionally emit a partial."""
        if not isinstance(frame, AudioFrame):
            raise TypeError("Rolling recognizer requires an AudioFrame.")
        self._validate_frame(frame)
        if len(self._buffer) + len(frame.data) > self._maximum_buffer_bytes:
            raise ValueError("Rolling recognition exceeded its utterance limit.")

        self._buffer.extend(frame.data)
        self._bytes_since_partial += len(frame.data)
        self._next_frame_sequence += 1
        if self._bytes_since_partial < self._partial_interval_bytes:
            return None
        self._bytes_since_partial %= self._partial_interval_bytes

        try:
            transcript = await self._service.transcribe(self._captured_audio())
        except SpeechInputServiceError as error:
            if error.code == "empty_transcript":
                return None
            raise

        stable_text = self._stabilizer.observe(transcript.text)
        if stable_text is None:
            return None
        revision = TranscriptRevision(
            text=stable_text,
            revision=self._next_revision,
            detected_language=transcript.detected_language,
            confidence=transcript.confidence,
        )
        self._next_revision += 1
        return revision

    async def finalize(self) -> TranscriptRevision:
        """Transcribe the bounded utterance and release recognition state."""
        if not self.is_active:
            raise RuntimeError("Rolling recognizer has no active turn.")
        if not self._buffer:
            self.cancel()
            raise ValueError("Rolling recognizer received no audio.")
        try:
            transcript = await self._service.transcribe(self._captured_audio())
            return TranscriptRevision(
                text=transcript.text,
                revision=self._next_revision,
                is_final=True,
                detected_language=transcript.detected_language,
                confidence=transcript.confidence,
            )
        finally:
            self.cancel()

    def cancel(self) -> None:
        """Discard all temporary audio and transcript revision state."""
        self._session_id = None
        self._turn_id = None
        self._sample_rate_hz = 0
        self._channels = 0
        self._sample_width_bytes = 0
        self._language = None
        self._buffer.clear()
        self._bytes_since_partial = 0
        self._next_frame_sequence = 1
        self._next_revision = 1
        self._stabilizer.reset()

    @property
    def _sample_stride_bytes(self) -> int:
        return self._channels * self._sample_width_bytes

    @property
    def _partial_interval_bytes(self) -> int:
        unaligned_bytes = max(
            self._sample_stride_bytes,
            int(
                self._sample_rate_hz
                * self._sample_stride_bytes
                * self._partial_interval_seconds
            ),
        )
        return unaligned_bytes - (unaligned_bytes % self._sample_stride_bytes)

    @property
    def _maximum_buffer_bytes(self) -> int:
        return int(
            self._sample_rate_hz
            * self._sample_stride_bytes
            * self._maximum_utterance_seconds
        )

    def _captured_audio(self) -> CapturedAudio:
        return CapturedAudio(
            data=bytes(self._buffer),
            sample_rate_hz=self._sample_rate_hz,
            channels=self._channels,
            sample_width_bytes=self._sample_width_bytes,
            language=self._language,
        )

    def _validate_frame(self, frame: AudioFrame) -> None:
        if self._session_id is None or self._turn_id is None:
            raise RuntimeError("Rolling recognizer has no active turn.")
        if frame.session_id != self._session_id or frame.turn_id != self._turn_id:
            raise ValueError("Audio frame belongs to a different recognition turn.")
        if frame.sequence != self._next_frame_sequence:
            raise ValueError("Audio frames must be accepted in sequence.")
        frame_format = (
            frame.sample_rate_hz,
            frame.channels,
            frame.sample_width_bytes,
        )
        expected_format = (
            self._sample_rate_hz,
            self._channels,
            self._sample_width_bytes,
        )
        if frame_format != expected_format:
            raise ValueError("Audio frame format changed during recognition.")


class _RevisionStabilizer:
    def __init__(self) -> None:
        self._presented = ""
        self._pending_revision = ""

    def reset(self) -> None:
        self._presented = ""
        self._pending_revision = ""

    def observe(self, text: str) -> str | None:
        candidate = " ".join(text.split())
        if not candidate:
            return None
        if not self._presented:
            return self._accept(candidate)

        presented_key = self._presented.casefold()
        candidate_key = candidate.casefold()
        if candidate_key == presented_key:
            self._pending_revision = ""
            return None
        if presented_key.startswith(candidate_key):
            self._pending_revision = ""
            return None
        if _is_related_growth(presented_key, candidate_key):
            return self._accept(candidate)
        if self._pending_revision and (
            candidate_key == self._pending_revision.casefold()
            or _is_related_growth(self._pending_revision.casefold(), candidate_key)
        ):
            return self._accept(candidate)
        self._pending_revision = candidate
        return None

    def _accept(self, text: str) -> str:
        self._presented = text
        self._pending_revision = ""
        return text


def _is_related_growth(previous: str, candidate: str) -> bool:
    if len(candidate) <= len(previous):
        return False
    if candidate.startswith(previous):
        return True
    similarity = SequenceMatcher(None, previous, candidate, autojunk=False).ratio()
    prefix_length = 0
    for previous_character, candidate_character in zip(
        previous,
        candidate,
        strict=False,
    ):
        if previous_character != candidate_character:
            break
        prefix_length += 1
    return similarity >= 0.72 or prefix_length / max(1, len(previous)) >= 0.55
