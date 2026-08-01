"""Prototype bridge from existing Qt capture snapshots to bounded frames."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from project_akiha.providers.voice import CapturedAudio


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """One bounded PCM frame owned by a single session and turn."""

    session_id: str
    turn_id: int
    sequence: int
    captured_at_ns: int
    data: bytes
    sample_rate_hz: int
    channels: int
    sample_width_bytes: int

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("Audio frame session ID cannot be empty.")
        if self.turn_id < 1:
            raise ValueError("Audio frame turn ID must be positive.")
        if self.sequence < 1:
            raise ValueError("Audio frame sequence must be positive.")
        if self.captured_at_ns < 0:
            raise ValueError("Audio frame timestamp cannot be negative.")
        if not self.data:
            raise ValueError("Audio frame data cannot be empty.")
        if self.sample_rate_hz <= 0:
            raise ValueError("Audio frame sample rate must be positive.")
        if self.channels <= 0 or self.sample_width_bytes <= 0:
            raise ValueError("Audio frame format values must be positive.")
        if len(self.data) % self.sample_stride_bytes:
            raise ValueError("Audio frame data must end on a sample boundary.")

    @property
    def sample_stride_bytes(self) -> int:
        return self.channels * self.sample_width_bytes

    @property
    def duration_seconds(self) -> float:
        sample_count = len(self.data) / self.sample_stride_bytes
        return sample_count / self.sample_rate_hz


class QtSnapshotAudioFrameBridge:
    """Extract incremental frames without acquiring a microphone itself."""

    def __init__(
        self,
        *,
        maximum_frame_duration_ms: int = 100,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if maximum_frame_duration_ms <= 0:
            raise ValueError("Maximum frame duration must be positive.")
        self._maximum_frame_duration_ms = maximum_frame_duration_ms
        self._clock_ns = clock_ns
        self._session_id: str | None = None
        self._turn_id: int | None = None
        self._last_snapshot: CapturedAudio | None = None
        self._next_sequence = 1

    @property
    def is_active(self) -> bool:
        return self._session_id is not None

    def start(self, *, session_id: str, turn_id: int) -> None:
        """Begin adapting snapshots from one existing capture operation."""
        if self.is_active:
            raise RuntimeError("Qt audio-frame bridge is already active.")
        if not session_id.strip():
            raise ValueError("Bridge session ID cannot be empty.")
        if turn_id < 1:
            raise ValueError("Bridge turn ID must be positive.")
        self._session_id = session_id.strip()
        self._turn_id = turn_id
        self._last_snapshot = None
        self._next_sequence = 1

    def stop(self) -> None:
        """Forget temporary PCM ownership without affecting Qt capture."""
        self._session_id = None
        self._turn_id = None
        self._last_snapshot = None
        self._next_sequence = 1

    def accept_snapshot(self, audio: CapturedAudio) -> tuple[AudioFrame, ...]:
        """Return frames containing only PCM appended since the prior snapshot."""
        if self._session_id is None or self._turn_id is None:
            raise RuntimeError("Qt audio-frame bridge is not active.")
        self._validate_sample_alignment(audio)

        previous = self._last_snapshot
        if previous is not None:
            self._validate_format(previous, audio)
            if len(audio.data) < len(previous.data):
                raise ValueError("Qt audio snapshot moved backwards.")
            if not audio.data.startswith(previous.data):
                raise ValueError("Qt audio snapshot changed previously emitted PCM.")
            new_data = audio.data[len(previous.data) :]
        else:
            new_data = audio.data

        self._last_snapshot = audio
        if not new_data:
            return ()

        maximum_bytes = self._maximum_frame_bytes(audio)
        frames: list[AudioFrame] = []
        for offset in range(0, len(new_data), maximum_bytes):
            data = new_data[offset : offset + maximum_bytes]
            frames.append(
                AudioFrame(
                    session_id=self._session_id,
                    turn_id=self._turn_id,
                    sequence=self._next_sequence,
                    captured_at_ns=self._clock_ns(),
                    data=data,
                    sample_rate_hz=audio.sample_rate_hz,
                    channels=audio.channels,
                    sample_width_bytes=audio.sample_width_bytes,
                )
            )
            self._next_sequence += 1
        return tuple(frames)

    def _maximum_frame_bytes(self, audio: CapturedAudio) -> int:
        sample_stride = audio.channels * audio.sample_width_bytes
        samples = max(
            1,
            audio.sample_rate_hz * self._maximum_frame_duration_ms // 1000,
        )
        return samples * sample_stride

    @staticmethod
    def _validate_sample_alignment(audio: CapturedAudio) -> None:
        sample_stride = audio.channels * audio.sample_width_bytes
        if len(audio.data) % sample_stride:
            raise ValueError("Qt audio snapshot ended between PCM samples.")

    @staticmethod
    def _validate_format(previous: CapturedAudio, current: CapturedAudio) -> None:
        previous_format = (
            previous.sample_rate_hz,
            previous.channels,
            previous.sample_width_bytes,
        )
        current_format = (
            current.sample_rate_hz,
            current.channels,
            current.sample_width_bytes,
        )
        if current_format != previous_format:
            raise ValueError("Qt audio format changed during an active turn.")
