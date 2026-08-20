"""Bounded concurrent synthesis with strictly ordered segment playback."""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from typing import Protocol

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_playback_controller import VoicePlaybackController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import ResponseSegment
from project_akiha.providers.voice import SynthesizedAudio
from project_akiha.services.speech_output import SpeechOutputService
from project_akiha.ui.voice_synthesis_worker import VoiceSynthesisThread

_LOGGER = logging.getLogger("project_akiha.voice.synthesis")


class _SynthesisThread(Protocol):
    audio_ready: object
    synthesis_failed: object
    synthesis_cancelled: object
    finished: object

    def start(self) -> None:
        """Start synthesis."""

    def cancel(self) -> None:
        """Request cancellation."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion."""


class StreamingVoiceOutputController:
    """Overlap bounded synthesis while retaining deterministic playback order."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        playback_controller: VoicePlaybackController,
        service: SpeechOutputService,
        *,
        maximum_concurrent_synthesis: int = 2,
        maximum_prefetched_segments: int = 3,
        maximum_queued_segments: int = 24,
        maximum_queued_characters: int = 8_000,
        on_response_spoken: Callable[[str, float], None] | None = None,
        thread_factory: Callable[
            [SpeechOutputService, str, str | None, str, float],
            _SynthesisThread,
        ] = VoiceSynthesisThread,
    ) -> None:
        if maximum_concurrent_synthesis < 1:
            raise ValueError("streaming synthesis concurrency must be positive.")
        if maximum_queued_segments < maximum_concurrent_synthesis:
            raise ValueError("streaming segment queue is smaller than concurrency.")
        if maximum_prefetched_segments < maximum_concurrent_synthesis:
            raise ValueError("streaming prefetch is smaller than concurrency.")
        if maximum_queued_characters < 1:
            raise ValueError("streaming character queue must be positive.")

        self._voice_controller = voice_controller
        self._event_bus = event_bus
        self._playback_controller = playback_controller
        self._service = service
        self._maximum_concurrent_synthesis = maximum_concurrent_synthesis
        self._maximum_prefetched_segments = maximum_prefetched_segments
        self._maximum_queued_segments = maximum_queued_segments
        self._maximum_queued_characters = maximum_queued_characters
        self._on_response_spoken = on_response_spoken
        self._thread_factory = thread_factory

        self._response_id: str | None = None
        self._next_submission_index = 0
        self._next_playback_index = 0
        self._final_segment_index: int | None = None
        self._pending: deque[ResponseSegment] = deque()
        self._active: dict[int, tuple[_SynthesisThread, ResponseSegment]] = {}
        self._cancelled_threads: set[_SynthesisThread] = set()
        self._ready_audio: dict[int, SynthesizedAudio] = {}
        self._segments: dict[int, ResponseSegment] = {}
        self._failed_indices: set[int] = set()
        self._played_segments: list[ResponseSegment] = []
        self._queued_characters = 0
        self._playback_active = False
        self._playing_index: int | None = None

        event_bus.subscribe(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            self._handle_stop_requested,
        )

    @property
    def is_active(self) -> bool:
        """Return whether a streamed response owns synthesis or playback."""
        return self._response_id is not None

    @property
    def queued_segment_count(self) -> int:
        """Return bounded accepted work without exposing response text."""
        return len(self._segments)

    def apply_service(self, service: SpeechOutputService) -> None:
        """Cancel current derived output and use a new provider next time."""
        self.cancel(wait_ms=0)
        self._service = service

    def submit(self, segment: ResponseSegment) -> bool:
        """Accept one ordered speech segment when automatic output is enabled."""
        config = self._voice_controller.config
        if not config.automatic_speech_enabled or not config.output_enabled:
            return False

        if self.is_active and segment.response_id != self._response_id:
            self.cancel(wait_ms=0)
        if not self.is_active and not self._start_response(segment):
            return False
        if segment.response_id != self._response_id:
            return False
        if segment.segment_index != self._next_submission_index:
            self._reject_stream(
                "speech_segment_order",
                "A speech segment arrived out of order.",
            )
            return False
        if self._final_segment_index is not None:
            self._reject_stream(
                "speech_segment_after_final",
                "A speech segment arrived after the final segment.",
            )
            return False
        if (
            len(self._segments) >= self._maximum_queued_segments
            or self._queued_characters + len(segment.speech_text)
            > self._maximum_queued_characters
        ):
            self._reject_stream(
                "speech_queue_full",
                "Streaming speech paused because its bounded queue filled.",
            )
            return False

        self._segments[segment.segment_index] = segment
        self._pending.append(segment)
        self._queued_characters += len(segment.speech_text)
        self._next_submission_index += 1
        if segment.is_final:
            self._final_segment_index = segment.segment_index
        self._fill_synthesis_slots()
        return True

    def cancel(self, wait_ms: int = 2_000) -> None:
        """Cancel queued synthesis and playback, then reject late callbacks."""
        threads = {
            *(thread for thread, _segment in self._active.values()),
            *self._cancelled_threads,
        }
        for thread in threads:
            thread.cancel()
            self._cancelled_threads.add(thread)
        unfinished = sum(
            1 for thread in threads if wait_ms > 0 and not thread.wait(wait_ms)
        )
        self._playback_controller.cancel()
        self._clear_response_state()
        if self._owns_output_operation():
            self._voice_controller.recover()
        if unfinished:
            raise RuntimeError(
                f"{unfinished} streaming synthesis worker(s) did not stop."
            )

    def _start_response(self, segment: ResponseSegment) -> bool:
        if segment.segment_index != 0:
            return False
        if not self._voice_controller.begin_streaming_output():
            return False
        self._response_id = segment.response_id
        return True

    def _fill_synthesis_slots(self) -> None:
        while (
            self._pending
            and len(self._active) < self._maximum_concurrent_synthesis
            and self._prefetched_segment_count() < self._maximum_prefetched_segments
        ):
            self._start_synthesis(self._pending.popleft())

    def _start_synthesis(self, segment: ResponseSegment) -> None:
        config = self._voice_controller.config
        thread = self._thread_factory(
            self._service,
            segment.speech_text,
            config.output_voice_id,
            "ja-JP",
            min(
                2.0,
                max(
                    0.5,
                    config.speaking_rate * segment.speaking_rate_multiplier,
                ),
            ),
        )
        index = segment.segment_index
        thread.audio_ready.connect(
            lambda audio, worker=thread, item=segment: self._handle_audio_ready(
                worker,
                item,
                audio,
            )
        )
        thread.synthesis_failed.connect(
            lambda code, message, worker=thread, item=segment: (
                self._handle_synthesis_failure(worker, item, code, message)
            )
        )
        thread.synthesis_cancelled.connect(
            lambda worker=thread: self._handle_synthesis_cancelled(worker)
        )
        thread.finished.connect(
            lambda worker=thread, segment_index=index: self._handle_thread_finished(
                worker,
                segment_index,
            )
        )
        self._active[index] = (thread, segment)
        thread.start()

    def _handle_audio_ready(
        self,
        thread: _SynthesisThread,
        segment: ResponseSegment,
        audio: object,
    ) -> None:
        if not self._accepts_callback(thread, segment):
            return
        if segment.segment_index in self._failed_indices:
            return
        if not isinstance(audio, SynthesizedAudio):
            self._fail_segment(segment.segment_index, "invalid_synthesized_audio")
            return
        self._ready_audio[segment.segment_index] = audio
        self._try_play_next()

    def _handle_synthesis_failure(
        self,
        thread: _SynthesisThread,
        segment: ResponseSegment,
        code: str,
        message: str,
    ) -> None:
        if not self._accepts_callback(thread, segment):
            return
        _LOGGER.warning(
            "Speech segment synthesis failed code=%s",
            code.strip() or "synthesis_failed",
        )
        del message
        self._fail_segment(segment.segment_index, code)

    def _handle_synthesis_cancelled(self, thread: _SynthesisThread) -> None:
        if thread not in self._cancelled_threads:
            return

    def _handle_thread_finished(
        self,
        thread: _SynthesisThread,
        segment_index: int,
    ) -> None:
        active = self._active.get(segment_index)
        if active is not None and active[0] is thread:
            self._active.pop(segment_index, None)
        self._cancelled_threads.discard(thread)
        self._fill_synthesis_slots()
        self._try_play_next()
        self._maybe_finish_response()

    def _fail_segment(self, segment_index: int, code: str) -> None:
        if (
            segment_index < self._next_playback_index
            or segment_index in self._failed_indices
        ):
            return
        self._failed_indices.add(segment_index)
        self._voice_controller.notify_error(
            code.strip() or "synthesis_failed",
            "A speech segment could not be synthesized; the text remains visible.",
        )
        self._try_play_next()

    def _try_play_next(self) -> None:
        if self._playback_active or not self.is_active:
            return
        while self._next_playback_index in self._failed_indices:
            self._failed_indices.remove(self._next_playback_index)
            self._release_segment(self._next_playback_index)
            self._next_playback_index += 1

        audio = self._ready_audio.pop(self._next_playback_index, None)
        if audio is None:
            self._maybe_finish_response()
            return

        index = self._next_playback_index
        self._playback_active = True
        self._playing_index = index
        self._playback_controller.play(
            audio,
            recover_on_finish=False,
            on_finished=lambda: self._handle_playback_finished(index),
            on_error=lambda code, message: self._handle_playback_error(
                index,
                code,
                message,
            ),
        )

    def _handle_playback_finished(self, segment_index: int) -> None:
        if not self.is_active or segment_index != self._next_playback_index:
            return
        segment = self._segments.get(segment_index)
        if segment is not None:
            self._played_segments.append(segment)
        self._playback_active = False
        self._playing_index = None
        self._release_segment(segment_index)
        self._next_playback_index += 1
        self._fill_synthesis_slots()
        self._try_play_next()

    def _handle_playback_error(
        self,
        segment_index: int,
        code: str,
        message: str,
    ) -> None:
        del segment_index
        self._playback_active = False
        self._playing_index = None
        self._voice_controller.report_error(code, message)
        self.cancel(wait_ms=0)

    def _release_segment(self, segment_index: int) -> None:
        segment = self._segments.pop(segment_index, None)
        if segment is not None:
            self._queued_characters -= len(segment.speech_text)

    def _prefetched_segment_count(self) -> int:
        indices = set(self._active) | set(self._ready_audio)
        if self._playing_index is not None:
            indices.add(self._playing_index)
        return len(indices)

    def _maybe_finish_response(self) -> None:
        final_index = self._final_segment_index
        if (
            final_index is None
            or self._playback_active
            or self._next_playback_index <= final_index
            or self._pending
            or self._active
            or self._ready_audio
        ):
            return

        spoken_segments = tuple(self._played_segments)
        self._clear_response_state()
        if self._owns_output_operation():
            self._voice_controller.recover()
        if self._on_response_spoken is not None and spoken_segments:
            spoken_text = " ".join(segment.speech_text for segment in spoken_segments)
            self._on_response_spoken(spoken_text, 1.0)
        if spoken_segments:
            self._event_bus.publish(
                EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
                {
                    "source": "assistant_reply",
                    "delivery": "streaming",
                },
            )

    def _accepts_callback(
        self,
        thread: _SynthesisThread,
        segment: ResponseSegment,
    ) -> bool:
        active = self._active.get(segment.segment_index)
        return (
            self.is_active
            and segment.response_id == self._response_id
            and active is not None
            and active[0] is thread
            and thread not in self._cancelled_threads
        )

    def _reject_stream(self, code: str, message: str) -> None:
        self._voice_controller.notify_error(code, message)
        self.cancel(wait_ms=0)

    def _handle_stop_requested(self, event: Event) -> None:
        del event
        self.cancel(wait_ms=0)

    def _owns_output_operation(self) -> bool:
        return (
            self._voice_controller.operation == "output"
            and self._voice_controller.state
            in {VoiceState.THINKING, VoiceState.SPEAKING}
        )

    def _clear_response_state(self) -> None:
        self._response_id = None
        self._next_submission_index = 0
        self._next_playback_index = 0
        self._final_segment_index = None
        self._pending.clear()
        self._active.clear()
        self._ready_audio.clear()
        self._segments.clear()
        self._failed_indices.clear()
        self._played_segments.clear()
        self._queued_characters = 0
        self._playback_active = False
        self._playing_index = None
