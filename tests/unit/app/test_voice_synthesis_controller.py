"""Tests for speech synthesis worker coordination."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_synthesis_controller import VoiceSynthesisController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import SynthesizedAudio


class VoiceSynthesisControllerTest(unittest.TestCase):
    """Verify one TTS worker hands encoded audio directly to playback."""

    def test_success_hands_audio_to_direct_callback(self) -> None:
        bus, voice, _, threads, audio, errors = _build()

        _request_speech(bus)
        synthesized = SynthesizedAudio(b"RIFFprivate-audio")
        threads[0].audio_ready.emit(synthesized)

        self.assertEqual(audio, [synthesized])
        self.assertEqual(errors, [])
        self.assertEqual(voice.state, VoiceState.THINKING)

    def test_audio_is_not_published_in_voice_events(self) -> None:
        bus, _, _, threads, _, _ = _build()
        observed: list[Event] = []
        bus.subscribe(EventType.VOICE_STATE_CHANGED, observed.append)
        bus.subscribe(EventType.VOICE_ERROR_OCCURRED, observed.append)

        _request_speech(bus)
        threads[0].audio_ready.emit(SynthesizedAudio(b"RIFFprivate-audio"))

        self.assertNotIn(
            b"RIFFprivate-audio",
            [value for event in observed for value in event.payload.values()],
        )

    def test_missing_playback_reports_error(self) -> None:
        bus, voice, _, threads, _, errors = _build(with_playback=False)

        _request_speech(bus)
        threads[0].audio_ready.emit(SynthesizedAudio(b"RIFFaudio"))

        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(errors[-1].payload["code"], "playback_unavailable")

    def test_provider_failure_reports_voice_error(self) -> None:
        bus, voice, _, threads, _, errors = _build()

        _request_speech(bus)
        threads[0].synthesis_failed.emit(
            "provider_unavailable",
            "VOICEVOX is offline.",
        )

        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(errors[-1].payload["code"], "provider_unavailable")

    def test_duplicate_request_cancels_worker_and_reports_busy(self) -> None:
        bus, voice, _, threads, audio, errors = _build()
        _request_speech(bus)

        _request_speech(bus, "A second line.")
        threads[0].audio_ready.emit(SynthesizedAudio(b"RIFFlate"))

        self.assertTrue(threads[0].cancelled)
        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(errors[-1].payload["code"], "synthesis_busy")
        self.assertEqual(audio, [])

    def test_stop_event_discards_late_audio(self) -> None:
        bus, voice, _, threads, audio, _ = _build()
        _request_speech(bus)

        bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)
        threads[0].audio_ready.emit(SynthesizedAudio(b"RIFFlate"))

        self.assertTrue(threads[0].cancelled)
        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(audio, [])

    def test_finished_worker_allows_next_request(self) -> None:
        bus, _, _, threads, _, _ = _build()
        _request_speech(bus)
        threads[0].finished.emit()
        bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)

        _request_speech(bus, "Next line.")

        self.assertEqual(len(threads), 2)
        self.assertTrue(threads[1].started)

    def test_service_update_cancels_active_request(self) -> None:
        bus, _, controller, threads, audio, _ = _build()
        _request_speech(bus)

        controller.apply_service(object())
        threads[0].audio_ready.emit(SynthesizedAudio(b"RIFFlate"))

        self.assertTrue(threads[0].cancelled)
        self.assertEqual(audio, [])

    def test_shutdown_wait_failure_is_reported(self) -> None:
        bus, _, controller, threads, _, _ = _build(thread_finished=False)
        _request_speech(bus)

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
        self.audio_ready = _Signal()
        self.synthesis_failed = _Signal()
        self.synthesis_cancelled = _Signal()
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
    with_playback: bool = True,
    thread_finished: bool = True,
) -> tuple[
    EventBus,
    VoiceController,
    VoiceSynthesisController,
    list[_Thread],
    list[SynthesizedAudio],
    list[Event],
]:
    bus = EventBus()
    voice = VoiceController(
        bus,
        VoiceConfig(
            enabled=True,
            output_voice_id="14",
            speaking_rate=1.2,
        ),
    )
    threads: list[_Thread] = []
    audio: list[SynthesizedAudio] = []

    def build_thread(
        service: object,
        text: str,
        voice_id: str | None,
        language: str,
        speaking_rate: float,
    ) -> _Thread:
        del service
        self_thread = _Thread(finished=thread_finished)
        self_thread.text = text
        self_thread.voice_id = voice_id
        self_thread.language = language
        self_thread.speaking_rate = speaking_rate
        threads.append(self_thread)
        return self_thread

    controller = VoiceSynthesisController(
        event_bus=bus,
        voice_controller=voice,
        service=object(),
        on_audio_synthesized=audio.append if with_playback else None,
        thread_factory=build_thread,
    )
    errors: list[Event] = []
    bus.subscribe(EventType.VOICE_ERROR_OCCURRED, errors.append)
    return bus, voice, controller, threads, audio, errors


def _request_speech(bus: EventBus, text: str = "Good morning.") -> None:
    bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": text})


if __name__ == "__main__":
    unittest.main()
