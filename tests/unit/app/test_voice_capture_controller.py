"""Tests for push-to-talk microphone capture orchestration."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.voice_capture_controller import VoiceCaptureController
from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import CapturedAudio, MicrophoneCaptureError


class VoiceCaptureControllerTest(unittest.TestCase):
    """Verify microphone bytes stay on the direct STT callback path."""

    def test_listen_request_starts_bounded_capture(self) -> None:
        bus, _, capture, _ = _build_controller()

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertTrue(capture.is_capturing)
        self.assertEqual(capture.timeout_seconds, 12)

    def test_stop_submits_audio_directly_without_event_payload(self) -> None:
        submitted: list[CapturedAudio] = []
        bus, voice, capture, events = _build_controller(submitted.append)
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        self.assertEqual(voice.state, VoiceState.THINKING)
        self.assertEqual(submitted[0].data, b"\x00\x01")
        self.assertFalse(capture.is_capturing)
        self.assertFalse(
            any(
                isinstance(value, (bytes, bytearray))
                for event in events
                for value in event.payload.values()
            )
        )

    def test_stop_without_stt_reports_unavailable(self) -> None:
        bus, voice, _, events = _build_controller()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED)

        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(_last_error(events)["code"], "speech_input_unavailable")

    def test_cancel_discards_capture(self) -> None:
        bus, voice, capture, _ = _build_controller()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_LISTEN_CANCEL_REQUESTED)

        self.assertTrue(capture.cancelled)
        self.assertFalse(capture.is_capturing)
        self.assertEqual(voice.state, VoiceState.IDLE)

    def test_capture_timeout_reports_error(self) -> None:
        bus, voice, capture, events = _build_controller()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        capture.trigger_timeout()

        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(_last_error(events)["code"], "capture_timeout")

    def test_device_error_reports_error(self) -> None:
        bus, voice, capture, events = _build_controller()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        capture.trigger_error("microphone_device_error", "Device disconnected.")

        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(_last_error(events)["code"], "microphone_device_error")

    def test_capture_start_failure_does_not_escape_event_handler(self) -> None:
        capture = _FakeCapture(start_error=MicrophoneCaptureError("busy", "Busy."))
        bus, voice, _, events = _build_controller(capture=capture)

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertEqual(voice.state, VoiceState.ERROR)
        self.assertEqual(_last_error(events)["code"], "busy")

    def test_rejected_listen_request_does_not_open_microphone(self) -> None:
        bus, _, capture, _ = _build_controller(config=VoiceConfig())

        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        self.assertFalse(capture.started)

    def test_config_change_cancels_capture_and_selects_device(self) -> None:
        bus, _, capture, _ = _build_controller()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        controller = capture.controller

        controller.apply_config(
            VoiceConfig(
                enabled=True,
                input_device="USB microphone",
                capture_timeout_seconds=20,
            )
        )

        self.assertTrue(capture.cancelled)
        self.assertEqual(capture.device_name, "USB microphone")

    def test_shutdown_cancel_is_idempotent(self) -> None:
        _, _, capture, _ = _build_controller()

        capture.controller.cancel()
        capture.controller.cancel()

        self.assertEqual(capture.cancel_count, 2)


class _FakeCapture:
    def __init__(
        self,
        *,
        start_error: MicrophoneCaptureError | None = None,
    ) -> None:
        self.is_capturing = False
        self.started = False
        self.cancelled = False
        self.cancel_count = 0
        self.timeout_seconds = 0
        self.device_name = ""
        self.start_error = start_error
        self.on_timeout: Callable[[], None] | None = None
        self.on_error: Callable[[str, str], None] | None = None
        self.controller: VoiceCaptureController

    def set_device_name(self, device_name: str) -> None:
        self.device_name = device_name

    def start(
        self,
        *,
        timeout_seconds: int,
        on_timeout: Callable[[], None],
        on_error: Callable[[str, str], None],
    ) -> None:
        self.started = True
        if self.start_error is not None:
            raise self.start_error
        self.is_capturing = True
        self.timeout_seconds = timeout_seconds
        self.on_timeout = on_timeout
        self.on_error = on_error

    def stop(self) -> CapturedAudio:
        self.is_capturing = False
        return CapturedAudio(data=b"\x00\x01", sample_rate_hz=16_000)

    def cancel(self) -> None:
        self.cancelled = True
        self.cancel_count += 1
        self.is_capturing = False

    def trigger_timeout(self) -> None:
        self.is_capturing = False
        assert self.on_timeout is not None
        self.on_timeout()

    def trigger_error(self, code: str, message: str) -> None:
        self.is_capturing = False
        assert self.on_error is not None
        self.on_error(code, message)


def _build_controller(
    on_audio_captured: Callable[[CapturedAudio], None] | None = None,
    *,
    config: VoiceConfig | None = None,
    capture: _FakeCapture | None = None,
) -> tuple[EventBus, VoiceController, _FakeCapture, list[Event]]:
    resolved_config = config or VoiceConfig(
        enabled=True,
        capture_timeout_seconds=12,
    )
    bus = EventBus()
    events: list[Event] = []
    for event_type in EventType:
        bus.subscribe(event_type, events.append)
    voice = VoiceController(bus, resolved_config)
    resolved_capture = capture or _FakeCapture()
    controller = VoiceCaptureController(
        event_bus=bus,
        voice_controller=voice,
        capture=resolved_capture,
        config=resolved_config,
        on_audio_captured=on_audio_captured,
    )
    resolved_capture.controller = controller
    return bus, voice, resolved_capture, events


def _last_error(events: list[Event]) -> dict[str, object]:
    return next(
        event.payload
        for event in reversed(events)
        if event.event_type == EventType.VOICE_ERROR_OCCURRED
    )


if __name__ == "__main__":
    unittest.main()
