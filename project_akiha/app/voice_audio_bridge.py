"""Adapt cumulative Qt microphone snapshots into bounded voice-session frames."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

from project_akiha.core.voice_session import AudioFrame
from project_akiha.providers.voice import CapturedAudio

_MAXIMUM_AUDIO_FRAME_BYTES = 1_048_576
_PREFIX_INTEGRITY_WINDOW_BYTES = 4_096


class CumulativeAudioFrameBridge:
    """Emit only newly appended PCM without retaining the cumulative recording."""

    def __init__(
        self,
        *,
        maximum_frame_duration_ms: int = 100,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 1 <= maximum_frame_duration_ms <= 1_000:
            raise ValueError("Maximum frame duration must be between 1 and 1000 ms.")
        self._maximum_frame_duration_ms = maximum_frame_duration_ms
        self._clock = clock
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._previous_length = 0
        self._previous_digest: bytes | None = None
        self._previous_digest_length = 0
        self._format: tuple[int, int, int] | None = None
        self._next_sequence_number = 0

    @property
    def is_active(self) -> bool:
        return self._session_id is not None

    def start_turn(self, *, session_id: str, turn_id: str) -> None:
        """Begin adapting cumulative snapshots owned by one voice turn."""
        if self.is_active:
            raise RuntimeError("Audio-frame bridge already owns a turn.")
        if not session_id.strip() or not turn_id.strip():
            raise ValueError("Audio-frame bridge IDs cannot be blank.")
        self._session_id = session_id
        self._turn_id = turn_id
        self._previous_length = 0
        self._previous_digest = None
        self._previous_digest_length = 0
        self._format = None
        self._next_sequence_number = 0

    def accept_snapshot(self, audio: CapturedAudio) -> tuple[AudioFrame, ...]:
        """Convert the appended suffix of one cumulative PCM snapshot into frames."""
        if self._session_id is None or self._turn_id is None:
            raise RuntimeError("Audio-frame bridge does not own a turn.")

        audio_format = (
            audio.sample_rate_hz,
            audio.channels,
            audio.sample_width_bytes,
        )
        if self._format is not None and audio_format != self._format:
            raise ValueError("Audio snapshot format changed during an active turn.")
        sample_stride = audio.channels * audio.sample_width_bytes
        if len(audio.data) % sample_stride:
            raise ValueError("Audio snapshot must end on a PCM sample boundary.")
        if len(audio.data) < self._previous_length:
            raise ValueError("Cumulative audio snapshot moved backwards.")
        if self._previous_digest is not None:
            prefix_start = self._previous_length - self._previous_digest_length
            current_prefix = audio.data[prefix_start : self._previous_length]
            if self._digest(current_prefix) != self._previous_digest:
                raise ValueError("Cumulative audio snapshot changed prior PCM.")

        appended = audio.data[self._previous_length :]
        self._previous_length = len(audio.data)
        digest_start = max(
            0,
            self._previous_length - _PREFIX_INTEGRITY_WINDOW_BYTES,
        )
        digest_source = audio.data[digest_start:]
        self._previous_digest = self._digest(digest_source)
        self._previous_digest_length = len(digest_source)
        self._format = audio_format
        if not appended:
            return ()

        maximum_bytes = self._maximum_frame_bytes(audio)
        frames: list[AudioFrame] = []
        for offset in range(0, len(appended), maximum_bytes):
            data = appended[offset : offset + maximum_bytes]
            frames.append(
                AudioFrame(
                    session_id=self._session_id,
                    turn_id=self._turn_id,
                    sequence_number=self._next_sequence_number,
                    captured_at_monotonic=self._clock(),
                    sample_rate_hz=audio.sample_rate_hz,
                    channels=audio.channels,
                    sample_width_bytes=audio.sample_width_bytes,
                    data=data,
                )
            )
            self._next_sequence_number += 1
        return tuple(frames)

    def release(self) -> None:
        """Release turn metadata and the non-reversible prior-prefix digest."""
        self._session_id = None
        self._turn_id = None
        self._previous_length = 0
        self._previous_digest = None
        self._previous_digest_length = 0
        self._format = None
        self._next_sequence_number = 0

    def _maximum_frame_bytes(self, audio: CapturedAudio) -> int:
        sample_stride = audio.channels * audio.sample_width_bytes
        samples = max(
            1,
            audio.sample_rate_hz * self._maximum_frame_duration_ms // 1_000,
        )
        requested = samples * sample_stride
        hard_limit = _MAXIMUM_AUDIO_FRAME_BYTES
        hard_limit -= hard_limit % sample_stride
        if hard_limit <= 0:
            raise ValueError("PCM sample stride exceeds the audio-frame byte limit.")
        return min(requested, hard_limit)

    @staticmethod
    def _digest(data: bytes) -> bytes:
        return hashlib.blake2s(data).digest()
