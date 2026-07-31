"""Tests for local speech recognition worker coordination."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_transcription_controller import (
    VoiceTranscriptionController,
)
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import CapturedAudio, VoiceTranscript


class VoiceTranscriptionControllerTest(unittest.TestCase):
    """Verify one STT worker feeds the editable transcript event path."""

    def test_success_publishes_transcript_and_returns_idle(self) -> None:
        bus, voice, controller, threads, transcripts, _ = _build()
        _begin_transcription(bus, controller)

        threads[0].transcript_ready.emit(VoiceTranscript("Recognized.", "en"))

        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(transcripts[-1].payload["text"], "Recognized.")

    def test_failure_reports_voice_error(self) -> None:
        bus, voice, controller, threads, _, errors = _build()
        _begin_transcription(bus, controller)

        threads[0].transcription_failed.emit(
            "provider_unavailable",
            "Provider unavailable.",
        )

        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "provider_unavailable")

    def test_duplicate_submission_reports_busy(self) -> None:
        bus, voice, controller, _, _, errors = _build()
        _begin_transcription(bus, controller)

        controller.submit(_audio())

        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "transcription_busy")

    def test_cancel_event_discards_worker_result(self) -> None:
        bus, voice, controller, threads, transcripts, _ = _build()
        _begin_transcription(bus, controller)

        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)
        threads[0].transcript_ready.emit(VoiceTranscript("Late result.", "en"))

        self.assertTrue(threads[0].cancelled)
        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(transcripts, [])

    def test_finished_worker_allows_next_submission(self) -> None:
        bus, _, controller, threads, _, _ = _build()
        _begin_transcription(bus, controller)
        threads[0].finished.emit()

        controller.submit(_audio())

        self.assertEqual(len(threads), 2)
        self.assertTrue(threads[1].started)

    def test_shutdown_wait_failure_is_reported(self) -> None:
        bus, _, controller, threads, _, _ = _build(thread_finished=False)
        _begin_transcription(bus, controller)

        with self.assertRaisesRegex(RuntimeError, "did not stop"):
            controller.cancel(wait_ms=25)

        self.assertEqual(threads[0].wait_ms, 25)

    def test_partial_transcript_keeps_listening_and_is_not_final(self) -> None:
        bus, voice, controller, threads, transcripts, _ = _build()
        partials: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.submit_partial(_audio(b"\x01\x00"))
        threads[0].transcript_ready.emit(VoiceTranscript("Interim words", "en"))

        self.assertEqual(voice.state, VoiceState.LISTENING)
        self.assertEqual(partials[-1].payload["text"], "Interim words")
        self.assertEqual(transcripts, [])

    def test_new_partial_snapshot_coalesces_while_worker_is_busy(self) -> None:
        bus, _, controller, threads, _, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        first = _audio(b"\x01\x00")
        second = _audio(b"\x02\x00")
        latest = _audio(b"\x03\x00")

        controller.submit_partial(first)
        controller.submit_partial(second)
        controller.submit_partial(latest)
        threads[0].finished.emit()

        self.assertEqual(len(threads), 2)
        self.assertEqual(threads[1].audio, latest)

    def test_partial_transcript_suppresses_duplicates_and_regressions(self) -> None:
        bus, _, controller, threads, _, _ = _build()
        partials: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.submit_partial(_audio(b"\x01\x00"))
        threads[0].transcript_ready.emit(VoiceTranscript("Open Downloads", "en"))
        threads[0].finished.emit()
        controller.submit_partial(_audio(b"\x02\x00"))
        threads[1].transcript_ready.emit(VoiceTranscript("Open Downloads", "en"))
        threads[1].finished.emit()
        controller.submit_partial(_audio(b"\x03\x00"))
        threads[2].transcript_ready.emit(VoiceTranscript("Open", "en"))

        self.assertEqual(
            [event.payload["text"] for event in partials],
            ["Open Downloads"],
        )

    def test_partial_transcript_accepts_related_growth_immediately(self) -> None:
        bus, _, controller, threads, _, _ = _build()
        partials: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.submit_partial(_audio(b"\x01\x00"))
        threads[0].transcript_ready.emit(VoiceTranscript("Open Downlods", "en"))
        threads[0].finished.emit()
        controller.submit_partial(_audio(b"\x02\x00"))
        threads[1].transcript_ready.emit(
            VoiceTranscript("Open Downloads directory", "en")
        )

        self.assertEqual(
            [event.payload["text"] for event in partials],
            ["Open Downlods", "Open Downloads directory"],
        )

    def test_partial_transcript_requires_confirmation_for_disruptive_rewrite(
        self,
    ) -> None:
        bus, _, controller, threads, _, _ = _build()
        partials: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        candidates = [
            "Open Chrome",
            "Launch the browser",
            "Launch the browser now",
        ]
        for index, candidate in enumerate(candidates, start=1):
            controller.submit_partial(_audio(bytes([index, 0])))
            threads[index - 1].transcript_ready.emit(VoiceTranscript(candidate, "en"))
            threads[index - 1].finished.emit()

        self.assertEqual(
            [event.payload["text"] for event in partials],
            ["Open Chrome", "Launch the browser now"],
        )

    def test_partial_stabilization_supports_japanese_without_word_boundaries(
        self,
    ) -> None:
        bus, _, controller, threads, _, _ = _build()
        partials: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.submit_partial(_audio(b"\x01\x00"))
        threads[0].transcript_ready.emit(VoiceTranscript("ダウンロード", "ja"))
        threads[0].finished.emit()
        controller.submit_partial(_audio(b"\x02\x00"))
        threads[1].transcript_ready.emit(VoiceTranscript("ダウンロードを開いて", "ja"))

        self.assertEqual(
            [event.payload["text"] for event in partials],
            ["ダウンロード", "ダウンロードを開いて"],
        )

    def test_new_recording_resets_partial_stabilization(self) -> None:
        bus, _, controller, threads, _, _ = _build()
        partials: list[Event] = []
        bus.subscribe(EventType.VOICE_TRANSCRIPT_PARTIAL, partials.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        controller.submit_partial(_audio(b"\x01\x00"))
        threads[0].transcript_ready.emit(VoiceTranscript("First command", "en"))
        threads[0].finished.emit()

        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        controller.submit_partial(_audio(b"\x02\x00"))
        threads[1].transcript_ready.emit(VoiceTranscript("Second", "en"))

        self.assertEqual(
            [event.payload["text"] for event in partials],
            ["First command", "Second"],
        )

    def test_final_recording_preempts_partial_and_retains_thinking_state(self) -> None:
        bus, voice, controller, threads, transcripts, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        controller.submit_partial(_audio(b"\x01\x00"))
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
        final_audio = _audio(b"\x02\x00")

        controller.submit(final_audio)

        self.assertTrue(threads[0].cancelled)
        threads[0].transcription_cancelled.emit()
        self.assertEqual(voice.state, VoiceState.THINKING)
        threads[0].finished.emit()
        self.assertEqual(threads[1].audio, final_audio)
        threads[1].transcript_ready.emit(VoiceTranscript("Final words", "en"))
        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(transcripts[-1].payload["text"], "Final words")

    def test_microphone_test_discards_text_and_publishes_pass_result(self) -> None:
        bus, voice, controller, threads, transcripts, _ = _build()
        completed: list[Event] = []
        bus.subscribe(EventType.VOICE_MICROPHONE_TEST_COMPLETED, completed.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        controller.submit_test(_audio())
        threads[0].transcript_ready.emit(VoiceTranscript("Private test words", "en"))

        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(transcripts, [])
        self.assertTrue(completed[-1].payload["text_present"])
        self.assertNotIn("text", completed[-1].payload)


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Thread:
    def __init__(self, audio: CapturedAudio, *, finished: bool) -> None:
        self.transcript_ready = _Signal()
        self.transcription_failed = _Signal()
        self.transcription_cancelled = _Signal()
        self.finished = _Signal()
        self.finished_result = finished
        self.started = False
        self.cancelled = False
        self.wait_ms = 0
        self.audio = audio

    def start(self) -> None:
        self.started = True

    def cancel(self) -> None:
        self.cancelled = True

    def wait(self, time: int = 0) -> bool:
        self.wait_ms = time
        return self.finished_result


def _build(
    *,
    thread_finished: bool = True,
) -> tuple[
    EventBus,
    VoiceController,
    VoiceTranscriptionController,
    list[_Thread],
    list[Event],
    list[Event],
]:
    bus = EventBus()
    voice = VoiceController(bus, VoiceConfig(enabled=True))
    threads: list[_Thread] = []

    def build_thread(_service: object, audio_value: CapturedAudio) -> _Thread:
        thread = _Thread(audio_value, finished=thread_finished)
        threads.append(thread)
        return thread

    controller = VoiceTranscriptionController(
        event_bus=bus,
        voice_controller=voice,
        service=object(),
        thread_factory=build_thread,
    )
    transcripts: list[Event] = []
    errors: list[Event] = []
    bus.subscribe(EventType.VOICE_TRANSCRIPT_READY, transcripts.append)
    bus.subscribe(EventType.VOICE_ERROR_OCCURRED, errors.append)
    return bus, voice, controller, threads, transcripts, errors


def _begin_transcription(
    bus: EventBus,
    controller: VoiceTranscriptionController,
) -> None:
    bus.publish(EventType.VOICE_LISTEN_REQUESTED)
    bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)
    controller.submit(_audio())


def _audio(data: bytes = b"\x00\x00") -> CapturedAudio:
    return CapturedAudio(data=data, sample_rate_hz=16_000)


if __name__ == "__main__":
    unittest.main()
