"""Bounded, turn-owned PCM storage for incremental voice recognition."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

from project_akiha.core.voice_session.models import AudioFrame

_MAXIMUM_BUFFER_DURATION_SECONDS = 900.0


@dataclass(frozen=True, slots=True)
class AudioBufferSnapshot:
    """Immutable bounded PCM copied from one active recognition turn."""

    session_id: str
    turn_id: str
    first_sequence_number: int
    last_sequence_number: int
    captured_from_monotonic: float
    captured_to_monotonic: float
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int
    data: bytes = field(repr=False)

    @property
    def sample_stride_bytes(self) -> int:
        return self.channels * self.sample_width_bytes

    @property
    def duration_seconds(self) -> float:
        return len(self.data) / self.sample_stride_bytes / self.sample_rate_hz


class RollingAudioBuffer:
    """Retain ordered PCM frames within a strict per-turn duration bound."""

    def __init__(self, *, maximum_duration_seconds: float = 30.0) -> None:
        if not 0 < maximum_duration_seconds <= _MAXIMUM_BUFFER_DURATION_SECONDS:
            raise ValueError(
                "Maximum audio-buffer duration must be between zero and 900 seconds."
            )
        self._maximum_duration_seconds = maximum_duration_seconds
        self._lock = threading.RLock()
        self._frames: deque[AudioFrame] = deque()
        self._session_id: str | None = None
        self._turn_id: str | None = None
        self._sample_rate_hz = 0
        self._channels = 0
        self._sample_width_bytes = 0
        self._maximum_bytes = 0
        self._retained_bytes = 0
        self._next_sequence_number = 0
        self._last_timestamp = -1.0
        self._evicted_frame_count = 0

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._session_id is not None

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            return self._retained_bytes

    @property
    def evicted_frame_count(self) -> int:
        with self._lock:
            return self._evicted_frame_count

    @property
    def duration_seconds(self) -> float:
        with self._lock:
            if not self._sample_rate_hz:
                return 0.0
            stride = self._channels * self._sample_width_bytes
            return self._retained_bytes / stride / self._sample_rate_hz

    def start_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        sample_rate_hz: int,
        channels: int,
        sample_width_bytes: int,
    ) -> None:
        """Claim bounded storage for one turn and one fixed PCM format."""
        with self._lock:
            if self._session_id is not None:
                raise RuntimeError("Rolling audio buffer already owns a turn.")
            if not session_id.strip() or not turn_id.strip():
                raise ValueError("Audio-buffer session and turn IDs cannot be blank.")
            if sample_rate_hz <= 0 or channels <= 0 or sample_width_bytes <= 0:
                raise ValueError("Audio-buffer PCM format values must be positive.")

            sample_stride = channels * sample_width_bytes
            maximum_bytes = int(
                sample_rate_hz * sample_stride * self._maximum_duration_seconds
            )
            maximum_bytes -= maximum_bytes % sample_stride
            if maximum_bytes < sample_stride:
                raise ValueError(
                    "Maximum audio-buffer duration is shorter than a sample."
                )

            self._session_id = session_id
            self._turn_id = turn_id
            self._sample_rate_hz = sample_rate_hz
            self._channels = channels
            self._sample_width_bytes = sample_width_bytes
            self._maximum_bytes = maximum_bytes
            self._next_sequence_number = 0
            self._last_timestamp = -1.0
            self._evicted_frame_count = 0

    def accept(self, frame: AudioFrame) -> None:
        """Append one ordered frame, evicting old frames before the bound is crossed."""
        with self._lock:
            self._validate_frame(frame)
            if len(frame.data) > self._maximum_bytes:
                raise ValueError(
                    "Audio frame exceeds the rolling-buffer duration bound."
                )

            while self._frames and (
                self._retained_bytes + len(frame.data) > self._maximum_bytes
            ):
                evicted = self._frames.popleft()
                self._retained_bytes -= len(evicted.data)
                self._evicted_frame_count += 1

            self._frames.append(frame)
            self._retained_bytes += len(frame.data)
            self._next_sequence_number += 1
            self._last_timestamp = frame.captured_at_monotonic

    def snapshot(self) -> AudioBufferSnapshot | None:
        """Copy the currently retained bounded window without releasing ownership."""
        with self._lock:
            if not self._frames:
                return None
            first = self._frames[0]
            last = self._frames[-1]
            return AudioBufferSnapshot(
                session_id=first.session_id,
                turn_id=first.turn_id,
                first_sequence_number=first.sequence_number,
                last_sequence_number=last.sequence_number,
                captured_from_monotonic=first.captured_at_monotonic,
                captured_to_monotonic=last.captured_at_monotonic,
                sample_rate_hz=first.sample_rate_hz,
                channels=first.channels,
                sample_width_bytes=first.sample_width_bytes,
                data=b"".join(frame.data for frame in self._frames),
            )

    def release(self) -> None:
        """Release all temporary PCM and turn ownership."""
        with self._lock:
            self._frames.clear()
            self._session_id = None
            self._turn_id = None
            self._sample_rate_hz = 0
            self._channels = 0
            self._sample_width_bytes = 0
            self._maximum_bytes = 0
            self._retained_bytes = 0
            self._next_sequence_number = 0
            self._last_timestamp = -1.0
            self._evicted_frame_count = 0

    def _validate_frame(self, frame: AudioFrame) -> None:
        if self._session_id is None or self._turn_id is None:
            raise RuntimeError("Rolling audio buffer does not own a turn.")
        if (frame.session_id, frame.turn_id) != (
            self._session_id,
            self._turn_id,
        ):
            raise ValueError("Audio frame belongs to a different buffer turn.")
        if frame.sequence_number != self._next_sequence_number:
            raise ValueError("Audio frames must be accepted in sequence.")
        if frame.captured_at_monotonic < self._last_timestamp:
            raise ValueError("Audio frame timestamps cannot move backwards.")
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
            raise ValueError("Audio frame format changed during an active turn.")
