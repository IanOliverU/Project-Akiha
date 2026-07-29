"""Tests for voice playback and runtime state coordination."""

from __future__ import annotations

import unittest

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_playback_controller import VoicePlaybackController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import AudioPlaybackError, SynthesizedAudio


class VoicePlaybackControllerTest(unittest.TestCase):
    """Verify playback callbacks drive speaking, completion, and errors."""

    def test_playback_start_and_finish_drive_voice_state(self) -> None:
        bus, voice, playback, controller, _ = _build()
        _request_speech(bus)

        controller.play(_audio())
        playback.start()
        self.assertEqual(voice.state, VoiceState.SPEAKING)

        playback.finish()
        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(voice.operation, "none")

    def test_playback_error_reports_voice_error(self) -> None:
        bus, voice, playback, controller, errors = _build()
        _request_speech(bus)
        controller.play(_audio())

        playback.fail("output_device_lost", "Output device disconnected.")

        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "output_device_lost")

    def test_immediate_playback_failure_reports_voice_error(self) -> None:
        bus, voice, _, controller, errors = _build(
            play_error=AudioPlaybackError("playback_busy", "Already playing.")
        )
        _request_speech(bus)

        controller.play(_audio())

        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "playback_busy")

    def test_stop_request_stops_playback_and_returns_idle(self) -> None:
        bus, voice, playback, controller, _ = _build()
        _request_speech(bus)
        controller.play(_audio())
        playback.start()

        bus.publish(EventType.VOICE_SPEAK_STOP_REQUESTED)

        self.assertTrue(playback.stopped)
        self.assertEqual(voice.state, VoiceState.IDLE)

    def test_unexpected_audio_is_rejected(self) -> None:
        _, voice, playback, controller, errors = _build()

        controller.play(_audio())

        self.assertFalse(playback.play_called)
        self.assertEqual(voice.state, VoiceState.IDLE)
        self.assertEqual(errors[-1].payload["code"], "unexpected_playback")

    def test_settings_are_applied_to_playback(self) -> None:
        _, _, playback, controller, _ = _build()

        controller.apply_config(
            VoiceConfig(output_device="Headphones", volume_percent=45)
        )

        self.assertEqual(playback.device_name, "Headphones")
        self.assertEqual(playback.volume_percent, 45)

    def test_shutdown_cancel_stops_playback(self) -> None:
        _, _, playback, controller, _ = _build()

        controller.cancel()

        self.assertTrue(playback.stopped)


class _Playback:
    def __init__(self, play_error: Exception | None = None) -> None:
        self.is_active = False
        self.play_error = play_error
        self.play_called = False
        self.stopped = False
        self.device_name = ""
        self.volume_percent = 100
        self._on_started = lambda: None
        self._on_finished = lambda: None
        self._on_error = lambda _code, _message: None

    def apply_settings(self, device_name: str, volume_percent: int) -> None:
        self.device_name = device_name
        self.volume_percent = volume_percent

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        on_started: object,
        on_finished: object,
        on_error: object,
    ) -> None:
        del audio
        self.play_called = True
        if self.play_error is not None:
            raise self.play_error
        self.is_active = True
        self._on_started = on_started
        self._on_finished = on_finished
        self._on_error = on_error

    def stop(self) -> None:
        self.stopped = True
        self.is_active = False

    def start(self) -> None:
        self._on_started()

    def finish(self) -> None:
        self.is_active = False
        self._on_finished()

    def fail(self, code: str, message: str) -> None:
        self.is_active = False
        self._on_error(code, message)


def _build(
    *,
    play_error: Exception | None = None,
) -> tuple[
    EventBus,
    VoiceController,
    _Playback,
    VoicePlaybackController,
    list[Event],
]:
    bus = EventBus()
    voice = VoiceController(bus, VoiceConfig(enabled=True))
    playback = _Playback(play_error)
    controller = VoicePlaybackController(bus, voice, playback)
    errors: list[Event] = []
    bus.subscribe(EventType.VOICE_ERROR_OCCURRED, errors.append)
    return bus, voice, playback, controller, errors


def _request_speech(bus: EventBus) -> None:
    bus.publish(EventType.VOICE_SPEAK_REQUESTED, {"text": "Good morning."})


def _audio() -> SynthesizedAudio:
    return SynthesizedAudio(b"RIFFprivate-wave")


if __name__ == "__main__":
    unittest.main()
