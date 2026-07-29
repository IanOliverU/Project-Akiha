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


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Thread:
    def __init__(self, *, finished: bool) -> None:
        self.transcript_ready = _Signal()
        self.transcription_failed = _Signal()
        self.transcription_cancelled = _Signal()
        self.finished = _Signal()
        self.finished_result = finished
        self.started = False
        self.cancelled = False
        self.wait_ms = 0

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

    def build_thread(_service: object, _audio_value: CapturedAudio) -> _Thread:
        thread = _Thread(finished=thread_finished)
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


def _audio() -> CapturedAudio:
    return CapturedAudio(data=b"\x00\x00", sample_rate_hz=16_000)


if __name__ == "__main__":
    unittest.main()
