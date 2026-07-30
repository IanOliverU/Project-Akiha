"""Tests for transcript-progress voice endpoint detection."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_endpoint_controller import VoiceEndpointController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState


class VoiceEndpointControllerTest(unittest.TestCase):
    def test_stops_after_partial_transcript_stops_growing(self) -> None:
        bus, voice, timer, stops, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, {"text": "Open"})
        bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, {"text": "Open"})
        bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, {"text": "Open Discord"})

        self.assertEqual(timer.started, [3000, 3000])
        timer.trigger()

        self.assertEqual(voice.state, VoiceState.THINKING)
        self.assertEqual(stops[-1].payload["reason"], "transcript_inactivity")

    def test_ignores_partial_transcript_until_listening(self) -> None:
        bus, _, timer, _, _ = _build()

        bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, {"text": "Open Discord"})

        self.assertEqual(timer.started, [])

    def test_manual_stop_disarms_transcript_endpoint(self) -> None:
        bus, _, timer, _, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, {"text": "Open Discord"})

        bus.publish(EventType.VOICE_LISTEN_STOP_REQUESTED, {"reason": "manual"})

        self.assertFalse(timer.armed)

    def test_apply_config_updates_timeout_and_can_disable_endpoint(self) -> None:
        bus, _, timer, _, controller = _build()
        controller.apply_config(
            VoiceConfig(
                enabled=True,
                auto_stop_on_silence_enabled=True,
                silence_timeout_seconds=1.5,
            )
        )
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)
        bus.publish(EventType.VOICE_TRANSCRIPT_PARTIAL, {"text": "Hello"})

        self.assertEqual(timer.started[-1], 1500)

        controller.apply_config(
            VoiceConfig(enabled=True, auto_stop_on_silence_enabled=False)
        )
        self.assertFalse(timer.armed)


class _Signal:
    def __init__(self) -> None:
        self._handlers: list[Callable[[], None]] = []

    def connect(self, handler: Callable[[], None]) -> None:
        self._handlers.append(handler)

    def emit(self) -> None:
        for handler in tuple(self._handlers):
            handler()


class _FakeTimer:
    def __init__(self) -> None:
        self.timeout = _Signal()
        self.single_shot = False
        self.started: list[int] = []
        self.armed = False

    def setSingleShot(self, single_shot: bool) -> None:
        self.single_shot = single_shot

    def start(self, milliseconds: int) -> None:
        self.started.append(milliseconds)
        self.armed = True

    def stop(self) -> None:
        self.armed = False

    def trigger(self) -> None:
        if not self.armed:
            return
        if self.single_shot:
            self.armed = False
        self.timeout.emit()


def _build() -> tuple[
    EventBus,
    VoiceController,
    _FakeTimer,
    list[Event],
    VoiceEndpointController,
]:
    config = VoiceConfig(
        enabled=True,
        auto_stop_on_silence_enabled=True,
        silence_timeout_seconds=3.0,
    )
    bus = EventBus()
    voice = VoiceController(bus, config)
    timer = _FakeTimer()
    stops: list[Event] = []
    bus.subscribe(EventType.VOICE_LISTEN_STOP_REQUESTED, stops.append)
    controller = VoiceEndpointController(
        bus,
        voice,
        config,
        timer_factory=lambda: timer,
    )
    return bus, voice, timer, stops, controller


if __name__ == "__main__":
    unittest.main()
