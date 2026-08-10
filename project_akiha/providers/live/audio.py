"""Bounded PCM framing for Gemini input and native-audio playback."""

from __future__ import annotations

import io
import wave

from project_akiha.core.voice_session import (
    AudioFrame,
    LiveSessionError,
    LiveSessionErrorCode,
)
from project_akiha.providers.voice import SynthesizedAudio

_INPUT_RATE_HZ = 16_000
_OUTPUT_RATE_HZ = 24_000
_CHANNELS = 1
_SAMPLE_WIDTH_BYTES = 2


class GeminiPcmInputChunker:
    """Normalize ordered Qt PCM into exact, low-latency Gemini chunks."""

    def __init__(self, *, chunk_duration_ms: int = 40) -> None:
        if not 20 <= chunk_duration_ms <= 100:
            raise ValueError("Gemini input chunks must be between 20 and 100 ms.")
        self._chunk_duration_ms = chunk_duration_ms
        self._buffer = bytearray()
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._expected_input_sequence = 0
        self._next_output_sequence = 0
        self._captured_at_monotonic = 0.0

    @property
    def is_active(self) -> bool:
        return self._session_id is not None

    def start_turn(self, *, session_id: str, turn_id: str) -> None:
        """Own one turn without acquiring the Qt microphone itself."""
        if self.is_active:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini input chunker already owns a turn.",
            )
        if not session_id.strip() or not turn_id.strip():
            raise ValueError("Gemini input chunker IDs cannot be blank.")
        self._session_id = session_id
        self._turn_id = turn_id
        self._expected_input_sequence = 0
        self._next_output_sequence = 0
        self._captured_at_monotonic = 0.0
        self._buffer.clear()

    def accept(self, frame: AudioFrame) -> tuple[AudioFrame, ...]:
        """Return zero or more fixed-size 16 kHz PCM16 chunks."""
        self._require_owned_frame(frame)
        self._expected_input_sequence += 1
        if not self._buffer:
            self._captured_at_monotonic = frame.captured_at_monotonic
        self._buffer.extend(frame.data)
        return self._take_complete_chunks()

    def finish(self) -> tuple[AudioFrame, ...]:
        """Flush a final chunk, padding only a sub-20 ms PCM tail."""
        self._require_active()
        emitted = list(self._take_complete_chunks())
        if self._buffer:
            minimum_bytes = self._duration_bytes(20)
            if len(self._buffer) < minimum_bytes:
                self._buffer.extend(b"\x00" * (minimum_bytes - len(self._buffer)))
            emitted.append(self._build_output(bytes(self._buffer)))
            self._buffer.clear()
        self.release()
        return tuple(emitted)

    def release(self) -> None:
        """Discard buffered microphone audio and release turn ownership."""
        self._buffer.clear()
        self._session_id = None
        self._turn_id = None
        self._expected_input_sequence = 0
        self._next_output_sequence = 0
        self._captured_at_monotonic = 0.0

    def _take_complete_chunks(self) -> tuple[AudioFrame, ...]:
        chunk_bytes = self._duration_bytes(self._chunk_duration_ms)
        emitted: list[AudioFrame] = []
        while len(self._buffer) >= chunk_bytes:
            data = bytes(self._buffer[:chunk_bytes])
            del self._buffer[:chunk_bytes]
            emitted.append(self._build_output(data))
        return tuple(emitted)

    def _build_output(self, data: bytes) -> AudioFrame:
        assert self._session_id is not None and self._turn_id is not None
        frame = AudioFrame(
            session_id=self._session_id,
            turn_id=self._turn_id,
            sequence_number=self._next_output_sequence,
            captured_at_monotonic=self._captured_at_monotonic,
            sample_rate_hz=_INPUT_RATE_HZ,
            channels=_CHANNELS,
            sample_width_bytes=_SAMPLE_WIDTH_BYTES,
            data=data,
        )
        self._next_output_sequence += 1
        self._captured_at_monotonic += frame.duration_seconds
        return frame

    def _require_owned_frame(self, frame: AudioFrame) -> None:
        self._require_active()
        if (frame.session_id, frame.turn_id) != (self._session_id, self._turn_id):
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The microphone frame belongs to a different live turn.",
            )
        if frame.sequence_number != self._expected_input_sequence:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "Gemini microphone frames arrived out of order.",
            )
        if (
            frame.sample_rate_hz,
            frame.channels,
            frame.sample_width_bytes,
        ) != (_INPUT_RATE_HZ, _CHANNELS, _SAMPLE_WIDTH_BYTES):
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
                "Gemini microphone input must be mono PCM16 at 16 kHz.",
            )

    def _require_active(self) -> None:
        if not self.is_active:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "The Gemini input chunker does not own a turn.",
            )

    @staticmethod
    def _duration_bytes(duration_ms: int) -> int:
        return _INPUT_RATE_HZ * _SAMPLE_WIDTH_BYTES * duration_ms // 1_000


class NativePcmWaveBuffer:
    """Convert ordered 24 kHz response PCM into short in-memory WAV segments."""

    def __init__(self, *, segment_duration_ms: int = 200) -> None:
        if not 100 <= segment_duration_ms <= 1_000:
            raise ValueError("Native playback segments must be 100 to 1000 ms.")
        self._segment_duration_ms = segment_duration_ms
        self._buffer = bytearray()
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._expected_sequence = 0

    @property
    def is_active(self) -> bool:
        return self._session_id is not None

    def start_turn(self, *, session_id: str, turn_id: str) -> None:
        """Begin buffering native output for one owned live turn."""
        if self.is_active:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "Native playback already owns a live turn.",
            )
        if not session_id.strip() or not turn_id.strip():
            raise ValueError("Native playback IDs cannot be blank.")
        self._session_id = session_id
        self._turn_id = turn_id
        self._expected_sequence = 0
        self._buffer.clear()

    def accept(self, frame: AudioFrame) -> tuple[SynthesizedAudio, ...]:
        """Buffer one native PCM frame and emit ready WAV segments."""
        self._require_owned_frame(frame)
        self._expected_sequence += 1
        self._buffer.extend(frame.data)
        segment_bytes = self._segment_bytes()
        emitted: list[SynthesizedAudio] = []
        while len(self._buffer) >= segment_bytes:
            pcm = bytes(self._buffer[:segment_bytes])
            del self._buffer[:segment_bytes]
            emitted.append(_pcm_to_wave(pcm, _OUTPUT_RATE_HZ))
        return tuple(emitted)

    def finish(self) -> tuple[SynthesizedAudio, ...]:
        """Flush the final response tail and release ownership."""
        self._require_active()
        emitted = (
            (_pcm_to_wave(bytes(self._buffer), _OUTPUT_RATE_HZ),)
            if self._buffer
            else ()
        )
        self.release()
        return emitted

    def release(self) -> None:
        """Discard pending provider audio and release the live turn."""
        self._buffer.clear()
        self._session_id = None
        self._turn_id = None
        self._expected_sequence = 0

    def _require_owned_frame(self, frame: AudioFrame) -> None:
        self._require_active()
        if (frame.session_id, frame.turn_id) != (self._session_id, self._turn_id):
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "Native response audio belongs to a different live turn.",
            )
        if frame.sequence_number != self._expected_sequence:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "Native response audio arrived out of order.",
            )
        if (
            frame.sample_rate_hz,
            frame.channels,
            frame.sample_width_bytes,
        ) != (_OUTPUT_RATE_HZ, _CHANNELS, _SAMPLE_WIDTH_BYTES):
            raise LiveSessionError(
                LiveSessionErrorCode.UNSUPPORTED_AUDIO_FORMAT,
                "Native response audio must be mono PCM16 at 24 kHz.",
            )

    def _require_active(self) -> None:
        if not self.is_active:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "Native playback does not own a live turn.",
            )

    def _segment_bytes(self) -> int:
        return (
            _OUTPUT_RATE_HZ * _SAMPLE_WIDTH_BYTES * self._segment_duration_ms // 1_000
        )


def _pcm_to_wave(data: bytes, sample_rate_hz: int) -> SynthesizedAudio:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(_CHANNELS)
        writer.setsampwidth(_SAMPLE_WIDTH_BYTES)
        writer.setframerate(sample_rate_hz)
        writer.writeframes(data)
    return SynthesizedAudio(
        data=output.getvalue(),
        media_type="audio/wav",
        sample_rate_hz=sample_rate_hz,
    )
