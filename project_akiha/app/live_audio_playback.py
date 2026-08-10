"""Feed hosted native PCM through Akiha's existing Qt playback owner."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.core.voice_session import (
    AudioFrame,
    LiveSessionError,
    LiveSessionErrorCode,
)
from project_akiha.providers.live.audio import NativePcmWaveBuffer
from project_akiha.providers.voice import SynthesizedAudio


class _PlaybackOwner(Protocol):
    def play(
        self,
        audio: SynthesizedAudio,
        *,
        recover_on_finish: bool = ...,
        on_finished: Callable[[], None] | None = ...,
        on_error: Callable[[str, str], None] | None = ...,
    ) -> None:
        """Play one in-memory WAV through the existing Qt owner."""

    def cancel(self) -> None:
        """Stop current playback and release its in-memory buffer."""


class NativeAudioPlaybackQueue:
    """Bound native response buffering without creating another audio device."""

    def __init__(
        self,
        playback: _PlaybackOwner,
        *,
        maximum_queued_segments: int = 600,
        segment_duration_ms: int = 200,
    ) -> None:
        if maximum_queued_segments <= 0:
            raise ValueError("Native playback queue capacity must be positive.")
        self._playback = playback
        self._maximum_queued_segments = maximum_queued_segments
        self._buffer = NativePcmWaveBuffer(segment_duration_ms=segment_duration_ms)
        self._queued: list[SynthesizedAudio] = []
        self._turn_active = False
        self._playing = False
        self._finishing = False
        self._generation = 0
        self._on_complete: Callable[[], None] | None = None
        self._on_error: Callable[[str, str], None] | None = None

    @property
    def is_active(self) -> bool:
        return self._turn_active

    @property
    def queued_segment_count(self) -> int:
        return len(self._queued) + int(self._playing)

    def start_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        on_complete: Callable[[], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        """Reserve the existing playback owner for one live response."""
        if self.is_active:
            raise LiveSessionError(
                LiveSessionErrorCode.INVALID_STATE,
                "Native playback already owns a live turn.",
            )
        self._generation += 1
        self._queued.clear()
        self._playing = False
        self._finishing = False
        self._on_complete = on_complete
        self._on_error = on_error
        self._buffer.start_turn(session_id=session_id, turn_id=turn_id)
        self._turn_active = True

    def submit(self, frame: AudioFrame) -> None:
        """Queue ready native-audio segments and start playback promptly."""
        emitted = self._buffer.accept(frame)
        self._append_bounded(emitted)
        self._play_next()

    def finish_turn(self) -> None:
        """Flush the final PCM tail and complete after queued playback."""
        emitted = self._buffer.finish()
        self._append_bounded(emitted)
        self._finishing = True
        self._play_next()
        self._complete_if_ready()

    def cancel(self) -> None:
        """Stop playback and discard all provider audio immediately."""
        self._generation += 1
        self._queued.clear()
        self._turn_active = False
        self._playing = False
        self._finishing = False
        self._buffer.release()
        self._on_complete = None
        self._on_error = None
        self._playback.cancel()

    def _append_bounded(self, audio: tuple[SynthesizedAudio, ...]) -> None:
        if len(self._queued) + len(audio) + int(self._playing) > (
            self._maximum_queued_segments
        ):
            self.cancel()
            raise LiveSessionError(
                LiveSessionErrorCode.AUDIO_BACKPRESSURE,
                "Gemini Live audio could not keep pace with playback.",
                retryable=True,
            )
        self._queued.extend(audio)

    def _play_next(self) -> None:
        if self._playing or not self._queued:
            return
        audio = self._queued.pop(0)
        self._playing = True
        generation = self._generation
        try:
            self._playback.play(
                audio,
                recover_on_finish=False,
                on_finished=lambda: self._handle_finished(generation),
                on_error=lambda code, message: self._handle_error(
                    generation,
                    code,
                    message,
                ),
            )
        except Exception:
            self._handle_error(
                generation,
                "native_playback_failed",
                "Native speech playback could not start.",
            )

    def _handle_finished(self, generation: int) -> None:
        if generation != self._generation or not self._playing:
            return
        self._playing = False
        self._play_next()
        self._complete_if_ready()

    def _handle_error(self, generation: int, code: str, message: str) -> None:
        if generation != self._generation:
            return
        callback = self._on_error
        self._generation += 1
        self._queued.clear()
        self._turn_active = False
        self._playing = False
        self._finishing = False
        self._buffer.release()
        self._on_complete = None
        self._on_error = None
        if callback is not None:
            callback(code.strip() or "native_playback_failed", message.strip())

    def _complete_if_ready(self) -> None:
        if not self._finishing or self._playing or self._queued:
            return
        callback = self._on_complete
        self._turn_active = False
        self._finishing = False
        self._on_complete = None
        self._on_error = None
        if callback is not None:
            callback()
