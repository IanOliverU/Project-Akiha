"""Tests for Settings voice diagnostics orchestration."""

from __future__ import annotations

import unittest
from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_diagnostics_controller import VoiceDiagnosticsController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import (
    VoiceProviderHealth,
    VoiceProviderStatus,
)
from project_akiha.services.voice_diagnostics import VoiceDiagnosticsSnapshot


class VoiceDiagnosticsControllerTest(unittest.TestCase):
    """Verify diagnostics never enter the conversation transcript path."""

    def test_health_check_presents_both_provider_results(self) -> None:
        _, _, controller, surface, threads = _build()

        controller.check_health()
        threads[0].diagnostics_ready.emit(
            VoiceDiagnosticsSnapshot(
                input_health=VoiceProviderHealth(
                    VoiceProviderStatus.AVAILABLE,
                    "Whisper ready.",
                ),
                output_health=VoiceProviderHealth(
                    VoiceProviderStatus.AVAILABLE,
                    "VOICEVOX ready.",
                ),
            )
        )

        self.assertEqual(
            surface.health,
            ("available", "Whisper ready.", "available", "VOICEVOX ready."),
        )
        self.assertEqual(surface.statuses[-1], ("Voice providers are ready.", False))

    def test_unavailable_health_is_visible(self) -> None:
        _, _, controller, surface, threads = _build()
        controller.check_health()

        threads[0].diagnostics_ready.emit(
            VoiceDiagnosticsSnapshot(
                input_health=VoiceProviderHealth(
                    VoiceProviderStatus.UNAVAILABLE,
                    "Model missing.",
                ),
                output_health=VoiceProviderHealth(
                    VoiceProviderStatus.AVAILABLE,
                    "VOICEVOX ready.",
                ),
            )
        )

        self.assertTrue(surface.statuses[-1][1])
        self.assertIn("attention", surface.statuses[-1][0])

    def test_microphone_test_uses_tagged_input_events(self) -> None:
        bus, voice, controller, surface, _ = _build()
        listen_events: list[object] = []
        stop_events: list[object] = []
        bus.subscribe(EventType.VOICE_LISTEN_REQUESTED, listen_events.append)
        bus.subscribe(EventType.VOICE_LISTEN_STOP_REQUESTED, stop_events.append)

        controller.toggle_microphone_test()
        controller.toggle_microphone_test()

        self.assertEqual(voice.state, VoiceState.THINKING)
        self.assertEqual(
            listen_events[-1].payload["source"],
            "settings_microphone_test",
        )
        self.assertEqual(
            stop_events[-1].payload["source"],
            "settings_microphone_test",
        )
        bus.publish(
            EventType.VOICE_MICROPHONE_TEST_COMPLETED,
            {"text_present": True},
        )
        self.assertEqual(surface.active[-1], ("microphone", False))
        self.assertIn("working", surface.statuses[-1][0])

    def test_output_test_tracks_playback_to_completion(self) -> None:
        _, voice, controller, surface, _ = _build()

        controller.toggle_output_test()
        voice.mark_speaking()
        voice.recover()

        self.assertEqual(surface.active[0], ("output", True))
        self.assertEqual(surface.active[-1], ("output", False))
        self.assertIn("playback", surface.statuses[-1][0])

    def test_busy_voice_rejects_test_without_changing_operation(self) -> None:
        bus, voice, controller, surface, _ = _build()
        bus.publish(EventType.VOICE_LISTEN_REQUESTED)

        controller.toggle_output_test()

        self.assertEqual(voice.state, VoiceState.LISTENING)
        self.assertTrue(surface.statuses[-1][1])


class _Signal:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def connect(self, handler: Callable[..., None]) -> None:
        self.handlers.append(handler)

    def emit(self, *args: object) -> None:
        for handler in tuple(self.handlers):
            handler(*args)


class _Thread:
    def __init__(self) -> None:
        self.diagnostics_ready = _Signal()
        self.diagnostics_failed = _Signal()
        self.finished = _Signal()
        self.started = False
        self.wait_ms = 0

    def start(self) -> None:
        self.started = True

    def wait(self, time: int = 0) -> bool:
        self.wait_ms = time
        return True


class _Surface:
    def __init__(self) -> None:
        self.health: tuple[str, str, str, str] | None = None
        self.statuses: list[tuple[str, bool]] = []
        self.active: list[tuple[str, bool]] = []

    def set_voice_health(
        self,
        input_status: str,
        input_detail: str,
        output_status: str,
        output_detail: str,
    ) -> None:
        self.health = (
            input_status,
            input_detail,
            output_status,
            output_detail,
        )

    def set_voice_diagnostic_status(
        self,
        status: str,
        is_error: bool = False,
    ) -> None:
        self.statuses.append((status, is_error))

    def set_voice_test_active(self, test_name: str, active: bool) -> None:
        self.active.append((test_name, active))


def _build() -> tuple[
    EventBus,
    VoiceController,
    VoiceDiagnosticsController,
    _Surface,
    list[_Thread],
]:
    bus = EventBus()
    voice = VoiceController(bus, VoiceConfig(enabled=True))
    surface = _Surface()
    threads: list[_Thread] = []

    def build_thread(_service: object) -> _Thread:
        thread = _Thread()
        threads.append(thread)
        return thread

    controller = VoiceDiagnosticsController(
        event_bus=bus,
        voice_controller=voice,
        service=object(),
        surface=surface,
        thread_factory=build_thread,
    )
    return bus, voice, controller, surface, threads


if __name__ == "__main__":
    unittest.main()
