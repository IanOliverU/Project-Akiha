"""Tests for bounded concurrent synthesis and ordered segment playback."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.streaming_voice_output_controller import (
    StreamingVoiceOutputController,
)
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import ResponseSegment
from project_akiha.providers.voice import SynthesizedAudio


class StreamingVoiceOutputControllerTest(unittest.TestCase):
    def test_synthesizes_concurrently_and_plays_strictly_in_order(self) -> None:
        context = _build(maximum_concurrent_synthesis=2)
        completions: list[Event] = []
        context.bus.subscribe(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            completions.append,
        )

        self.assertTrue(context.controller.submit(_segment(0, "First.")))
        self.assertTrue(context.controller.submit(_segment(1, "Second.")))
        self.assertTrue(context.controller.submit(_segment(2, "Third.", final=True)))
        self.assertEqual(len(context.threads), 2)

        context.threads[1].audio_ready.emit(_audio("second"))
        self.assertEqual(context.playback.played, [])

        context.threads[0].audio_ready.emit(_audio("first"))
        self.assertEqual(context.playback.played, ["first"])
        context.threads[0].finished.emit()
        self.assertEqual(len(context.threads), 3)
        context.threads[1].finished.emit()

        context.playback.finish()
        self.assertEqual(context.playback.played, ["first", "second"])
        context.threads[2].audio_ready.emit(_audio("third"))
        context.threads[2].finished.emit()
        context.playback.finish()
        self.assertEqual(context.playback.played, ["first", "second", "third"])

        context.playback.finish()

        self.assertFalse(context.controller.is_active)
        self.assertEqual(context.voice.state, VoiceState.IDLE)
        self.assertEqual(context.spoken_responses, [("First. Second. Third.", 1.0)])
        self.assertEqual(
            completions[-1].payload,
            {"source": "assistant_reply", "delivery": "streaming"},
        )

    def test_queue_limit_cancels_only_derived_speech(self) -> None:
        context = _build(
            maximum_concurrent_synthesis=1,
            maximum_queued_segments=2,
        )

        self.assertTrue(context.controller.submit(_segment(0, "First.")))
        self.assertTrue(context.controller.submit(_segment(1, "Second.")))
        self.assertFalse(context.controller.submit(_segment(2, "Third.", final=True)))

        self.assertFalse(context.controller.is_active)
        self.assertTrue(context.threads[0].cancelled)
        self.assertEqual(context.errors[-1].payload["code"], "speech_queue_full")
        self.assertNotIn("First.", context.errors[-1].payload.values())
        self.assertEqual(context.voice.state, VoiceState.IDLE)

    def test_audio_prefetch_remains_bounded_while_playback_is_slow(self) -> None:
        context = _build(maximum_concurrent_synthesis=2)
        for index in range(5):
            self.assertTrue(
                context.controller.submit(
                    _segment(index, f"Segment {index}.", final=index == 4)
                )
            )

        context.threads[0].audio_ready.emit(_audio("zero"))
        context.threads[1].audio_ready.emit(_audio("one"))
        context.threads[0].finished.emit()
        context.threads[1].finished.emit()
        context.threads[2].audio_ready.emit(_audio("two"))
        context.threads[2].finished.emit()

        self.assertEqual(len(context.threads), 3)
        self.assertEqual(context.playback.played, ["zero"])

        context.playback.finish()

        self.assertEqual(len(context.threads), 4)
        self.assertEqual(context.playback.played, ["zero", "one"])

    def test_synthesis_failure_skips_segment_without_hiding_later_audio(self) -> None:
        context = _build(maximum_concurrent_synthesis=1)
        context.controller.submit(_segment(0, "Unspoken first."))
        context.controller.submit(_segment(1, "Spoken second.", final=True))

        context.threads[0].synthesis_failed.emit(
            "provider_failed",
            "private provider detail",
        )
        context.threads[0].finished.emit()
        context.threads[1].audio_ready.emit(_audio("second"))
        context.threads[1].finished.emit()

        self.assertEqual(context.playback.played, ["second"])
        self.assertEqual(context.errors[-1].payload["code"], "provider_failed")
        self.assertNotIn("private provider detail", context.errors[-1].payload.values())

        context.playback.finish()

        self.assertFalse(context.controller.is_active)
        self.assertEqual(context.spoken_responses, [("Spoken second.", 1.0)])

    def test_stop_discards_queued_audio_and_late_callbacks(self) -> None:
        context = _build()
        completions: list[Event] = []
        context.bus.subscribe(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            completions.append,
        )
        context.controller.submit(_segment(0, "Cancelled.", final=True))

        context.bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        context.threads[0].audio_ready.emit(_audio("late"))

        self.assertTrue(context.threads[0].cancelled)
        self.assertEqual(context.playback.played, [])
        self.assertFalse(context.controller.is_active)
        self.assertEqual(context.voice.state, VoiceState.IDLE)
        self.assertEqual(completions, [])

    def test_configured_and_identity_rates_are_combined_per_segment(self) -> None:
        context = _build(speaking_rate=1.2)

        context.controller.submit(
            _segment(0, "Measured.", final=True, rate_multiplier=0.94)
        )

        self.assertAlmostEqual(context.threads[0].speaking_rate, 1.128)

    def test_automatic_speech_setting_gates_stream_before_state_changes(self) -> None:
        context = _build(automatic_speech_enabled=False)

        accepted = context.controller.submit(_segment(0, "Silent.", final=True))

        self.assertFalse(accepted)
        self.assertEqual(context.threads, [])
        self.assertEqual(context.voice.state, VoiceState.IDLE)


class _Signal:
    def __init__(self) -> None:
        self._handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self._handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self._handlers):
            handler(*args)


class _Thread:
    def __init__(self) -> None:
        self.audio_ready = _Signal()
        self.synthesis_failed = _Signal()
        self.synthesis_cancelled = _Signal()
        self.finished = _Signal()
        self.started = False
        self.cancelled = False
        self.wait_ms = 0
        self.text = ""
        self.speaking_rate = 1.0

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, time: int = 0) -> bool:
        self.wait_ms = time
        return True


class _PlaybackController:
    def __init__(self, voice: VoiceController) -> None:
        self._voice = voice
        self.played: list[str] = []
        self.cancelled = False
        self._on_finished: Callable[[], None] | None = None
        self._on_error: Callable[[str, str], None] | None = None

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        recover_on_finish: bool,
        on_finished: Callable[[], None],
        on_error: Callable[[str, str], None],
    ) -> None:
        self.played.append(audio.data.decode("utf-8"))
        self._on_finished = on_finished
        self._on_error = on_error
        self._voice.mark_speaking()
        self.assert_streaming(recover_on_finish)

    def cancel(self) -> None:
        self.cancelled = True
        self._on_finished = None
        self._on_error = None

    def finish(self) -> None:
        callback = self._on_finished
        self._on_finished = None
        if callback is not None:
            callback()

    @staticmethod
    def assert_streaming(recover_on_finish: bool) -> None:
        if recover_on_finish:
            raise AssertionError("streamed segments must retain output ownership")


class _Context:
    def __init__(
        self,
        bus: EventBus,
        voice: VoiceController,
        controller: StreamingVoiceOutputController,
        playback: _PlaybackController,
        threads: list[_Thread],
        errors: list[Event],
        spoken_responses: list[tuple[str, float]],
    ) -> None:
        self.bus = bus
        self.voice = voice
        self.controller = controller
        self.playback = playback
        self.threads = threads
        self.errors = errors
        self.spoken_responses = spoken_responses


def _build(
    *,
    automatic_speech_enabled: bool = True,
    speaking_rate: float = 1.0,
    maximum_concurrent_synthesis: int = 2,
    maximum_queued_segments: int = 6,
) -> _Context:
    bus = EventBus()
    voice = VoiceController(
        bus,
        VoiceConfig(
            enabled=True,
            automatic_speech_enabled=automatic_speech_enabled,
            speaking_rate=speaking_rate,
        ),
    )
    playback = _PlaybackController(voice)
    threads: list[_Thread] = []

    def build_thread(
        service: object,
        text: str,
        voice_id: str | None,
        language: str,
        rate: float,
    ) -> _Thread:
        del service, voice_id, language
        thread = _Thread()
        thread.text = text
        thread.speaking_rate = rate
        threads.append(thread)
        return thread

    spoken_responses: list[tuple[str, float]] = []
    controller = StreamingVoiceOutputController(
        bus,
        voice,
        playback,  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        maximum_concurrent_synthesis=maximum_concurrent_synthesis,
        maximum_queued_segments=maximum_queued_segments,
        on_response_spoken=lambda text, rate: spoken_responses.append((text, rate)),
        thread_factory=build_thread,
    )
    errors: list[Event] = []
    bus.subscribe(EventType.VOICE_ERROR_OCCURRED, errors.append)
    return _Context(
        bus,
        voice,
        controller,
        playback,
        threads,
        errors,
        spoken_responses,
    )


def _segment(
    index: int,
    text: str,
    *,
    final: bool = False,
    rate_multiplier: float = 1.0,
) -> ResponseSegment:
    return ResponseSegment(
        response_id="response-1",
        segment_index=index,
        canonical_text=text,
        speech_text=text,
        speaking_rate_multiplier=rate_multiplier,
        is_final=final,
    )


def _audio(label: str) -> SynthesizedAudio:
    return SynthesizedAudio(label.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
