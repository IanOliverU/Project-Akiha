"""Coordinate Settings voice health checks and non-destructive tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from project_akiha.app.voice_controller import VoiceController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import VoiceProviderStatus
from project_akiha.services.voice_diagnostics import (
    VoiceDiagnosticsService,
    VoiceDiagnosticsSnapshot,
)
from project_akiha.ui.voice_diagnostics_worker import VoiceDiagnosticsThread

_VOICE_TEST_PHRASE = "こんにちは。音声テストです。"


class VoiceDiagnosticsSurface(Protocol):
    """Settings controls updated by voice diagnostics."""

    def set_voice_health(
        self,
        input_status: str,
        input_detail: str,
        output_status: str,
        output_detail: str,
    ) -> None:
        """Display provider health results."""

    def set_voice_diagnostic_status(self, status: str, is_error: bool = False) -> None:
        """Display the current diagnostic action."""

    def set_voice_test_active(self, test_name: str, active: bool) -> None:
        """Update test button state."""

    def set_microphone_activity(self, status: str) -> None:
        """Display privacy-safe microphone and endpoint activity."""


class _DiagnosticsThread(Protocol):
    diagnostics_ready: object
    diagnostics_failed: object
    finished: object

    def start(self) -> None:
        """Start diagnostics."""

    def wait(self, time: int = ...) -> bool:
        """Wait for completion."""


class VoiceDiagnosticsController:
    """Keep diagnostic actions separate from persisted conversation data."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        service: VoiceDiagnosticsService,
        surface: VoiceDiagnosticsSurface,
        *,
        thread_factory: Callable[
            [VoiceDiagnosticsService],
            _DiagnosticsThread,
        ] = VoiceDiagnosticsThread,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._service = service
        self._surface = surface
        self._thread_factory = thread_factory
        self._active_threads: list[_DiagnosticsThread] = []
        self._active_test: str | None = None

        event_bus.subscribe(
            EventType.VOICE_MICROPHONE_TEST_COMPLETED,
            self._handle_microphone_test_completed,
        )
        event_bus.subscribe(
            EventType.VOICE_MICROPHONE_ACTIVITY_UPDATED,
            self._handle_microphone_activity,
        )
        event_bus.subscribe(
            EventType.VOICE_STATE_CHANGED,
            self._handle_voice_state_changed,
        )
        event_bus.subscribe(
            EventType.VOICE_ERROR_OCCURRED,
            self._handle_voice_error,
        )

    def apply_service(self, service: VoiceDiagnosticsService) -> None:
        """Use updated providers for future health checks."""
        self._service = service

    def check_health(self) -> None:
        """Check STT and TTS providers without blocking Settings."""
        if self._active_threads:
            return
        self._surface.set_voice_diagnostic_status("Checking voice providers...")
        thread = self._thread_factory(self._service)
        thread.diagnostics_ready.connect(
            lambda snapshot, worker=thread: self._handle_health_ready(
                worker,
                snapshot,
            )
        )
        thread.diagnostics_failed.connect(
            lambda message, worker=thread: self._handle_health_failed(
                worker,
                message,
            )
        )
        thread.finished.connect(lambda worker=thread: self._remove_thread(worker))
        self._active_threads.append(thread)
        thread.start()

    def toggle_microphone_test(self) -> None:
        """Start or stop a transcript-discarding microphone test."""
        if self._active_test == "microphone":
            self._event_bus.publish(
                EventType.VOICE_LISTEN_STOP_REQUESTED,
                {"source": "settings_microphone_test"},
            )
            return
        if not self._can_start_test("microphone"):
            return
        self._active_test = "microphone"
        self._surface.set_voice_test_active("microphone", True)
        self._surface.set_microphone_activity("Waiting for microphone data...")
        self._surface.set_voice_diagnostic_status("Listening for microphone test...")
        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "settings_microphone_test"},
        )

    def toggle_output_test(self) -> None:
        """Start or stop a short Japanese synthesis and playback test."""
        if self._active_test == "output":
            self._event_bus.publish(
                EventType.VOICE_SPEAK_STOP_REQUESTED,
                {"source": "settings_output_test"},
            )
            self._finish_test("Voice test stopped.")
            return
        if not self._can_start_test("output"):
            return
        self._active_test = "output"
        self._surface.set_voice_test_active("output", True)
        self._surface.set_voice_diagnostic_status("Synthesizing Japanese voice test...")
        self._event_bus.publish(
            EventType.VOICE_SPEAK_REQUESTED,
            {
                "text": _VOICE_TEST_PHRASE,
                "source": "settings_output_test",
            },
        )

    def cancel(self, wait_ms: int = 2000) -> None:
        """Wait for health checks during shutdown."""
        unfinished = 0
        for thread in tuple(self._active_threads):
            if wait_ms > 0 and not thread.wait(wait_ms):
                unfinished += 1
        if unfinished:
            raise RuntimeError(f"{unfinished} voice diagnostic worker(s) did not stop.")

    def _can_start_test(self, test_name: str) -> bool:
        if (
            self._active_test is not None
            or self._voice_controller.state != VoiceState.IDLE
        ):
            self._surface.set_voice_diagnostic_status(
                "Voice is busy. Stop the current voice action first.",
                True,
            )
            return False
        config = self._voice_controller.config
        enabled = (
            config.input_enabled if test_name == "microphone" else config.output_enabled
        )
        if not enabled:
            self._surface.set_voice_diagnostic_status(
                f"{test_name.capitalize()} test is disabled by Voice settings.",
                True,
            )
            return False
        return True

    def _handle_health_ready(
        self,
        thread: _DiagnosticsThread,
        snapshot: object,
    ) -> None:
        if thread not in self._active_threads:
            return
        if not isinstance(snapshot, VoiceDiagnosticsSnapshot):
            self._surface.set_voice_diagnostic_status(
                "Voice diagnostics returned an invalid result.",
                True,
            )
            return
        input_health = snapshot.input_health
        output_health = snapshot.output_health
        self._surface.set_voice_health(
            input_health.status.value,
            input_health.detail,
            output_health.status.value,
            output_health.detail,
        )
        all_available = (
            input_health.status == VoiceProviderStatus.AVAILABLE
            and output_health.status == VoiceProviderStatus.AVAILABLE
        )
        self._surface.set_voice_diagnostic_status(
            (
                "Voice providers are ready."
                if all_available
                else "One or more voice providers need attention."
            ),
            not all_available,
        )

    def _handle_health_failed(
        self,
        thread: _DiagnosticsThread,
        message: str,
    ) -> None:
        if thread not in self._active_threads:
            return
        self._surface.set_voice_diagnostic_status(
            message.strip() or "Voice diagnostics failed.",
            True,
        )

    def _handle_microphone_test_completed(self, event: Event) -> None:
        if self._active_test == "microphone":
            confidence_level = event.payload.get("confidence_level")
            confidence_suffix = (
                f" ({confidence_level} confidence)"
                if confidence_level in {"low", "medium", "high"}
                else ""
            )
            self._finish_test(
                "Microphone and speech recognition are working" f"{confidence_suffix}."
            )

    def _handle_microphone_activity(self, event: Event) -> None:
        if self._active_test != "microphone":
            return
        activity = event.payload.get("activity")
        level = event.payload.get("level")
        if not isinstance(activity, str) or not isinstance(level, str):
            return
        if activity == "calibrating":
            status = "Calibrating room noise..."
        elif activity == "waiting":
            status = f"Waiting for speech ({level} level)."
        elif activity == "speaking":
            status = f"Speech detected ({level} level)."
        elif activity == "pause":
            remaining = event.payload.get("silence_remaining_seconds")
            if isinstance(remaining, (int, float)) and not isinstance(remaining, bool):
                status = f"Pause detected; finishing in {float(remaining):.1f} sec."
            else:
                status = "Pause detected."
        else:
            return
        self._surface.set_microphone_activity(status)

    def _handle_voice_state_changed(self, event: Event) -> None:
        if self._active_test != "output":
            return
        state = event.payload.get("state")
        operation = event.payload.get("operation")
        if state == "speaking" and operation == "output":
            self._surface.set_voice_diagnostic_status("Playing Japanese voice test...")
        elif state == "idle":
            self._finish_test("Voice synthesis and playback are working.")

    def _handle_voice_error(self, event: Event) -> None:
        if self._active_test is None:
            return
        message = event.payload.get("message")
        if not isinstance(message, str) or not message.strip():
            message = "Voice test failed."
        self._finish_test(message, is_error=True)

    def _finish_test(self, status: str, *, is_error: bool = False) -> None:
        test_name = self._active_test
        self._active_test = None
        if test_name is not None:
            self._surface.set_voice_test_active(test_name, False)
        if test_name == "microphone":
            self._surface.set_microphone_activity("Not active")
        self._surface.set_voice_diagnostic_status(status, is_error)

    def _remove_thread(self, thread: _DiagnosticsThread) -> None:
        if thread in self._active_threads:
            self._active_threads.remove(thread)
