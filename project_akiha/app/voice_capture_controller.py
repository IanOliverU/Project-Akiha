"""Wire push-to-talk events to temporary microphone capture."""

from __future__ import annotations

from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import (
    CapturedAudio,
    MicrophoneCapture,
    MicrophoneCaptureError,
)


class VoiceCaptureController:
    """Keep raw microphone audio on a direct, non-logging callback path."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        capture: MicrophoneCapture,
        config: VoiceConfig,
        on_audio_captured: Callable[[CapturedAudio], None] | None = None,
        on_audio_snapshot: Callable[[CapturedAudio], None] | None = None,
        on_microphone_test_captured: Callable[[CapturedAudio], None] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._capture = capture
        self._config = config
        self._on_audio_captured = on_audio_captured
        self._on_audio_snapshot = on_audio_snapshot
        self._on_microphone_test_captured = on_microphone_test_captured
        self._capture_source = "chat"

        event_bus.subscribe(
            EventType.VOICE_LISTEN_REQUESTED,
            self._handle_listen_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            self._handle_listen_stop_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_listen_cancel_requested,
        )

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply microphone selection and timeout settings."""
        device_changed = config.input_device != self._config.input_device
        input_disabled = not config.input_enabled or not config.push_to_talk_enabled
        if self._capture.is_capturing and (device_changed or input_disabled):
            self._capture.cancel()

        self._config = config
        try:
            self._capture.set_device_name(config.input_device)
        except MicrophoneCaptureError as error:
            self._voice_controller.report_error(error.code, str(error))

    def cancel(self) -> None:
        """Release the microphone during shutdown."""
        self._capture.cancel()

    def _handle_listen_requested(self, event: Event) -> None:
        if self._voice_controller.state != VoiceState.LISTENING:
            return
        source = event.payload.get("source")
        self._capture_source = source if isinstance(source, str) else "chat"

        try:
            self._capture.start(
                timeout_seconds=self._config.capture_timeout_seconds,
                on_timeout=self._handle_capture_timeout,
                on_error=self._handle_capture_error,
                on_audio_snapshot=(
                    self._handle_audio_snapshot
                    if self._config.live_transcription_enabled
                    else None
                ),
                on_silence=(
                    self._handle_silence
                    if self._config.auto_stop_on_silence_enabled
                    else None
                ),
                silence_timeout_seconds=self._config.silence_timeout_seconds,
                auto_stop_on_silence=self._config.auto_stop_on_silence_enabled,
            )
        except MicrophoneCaptureError as error:
            self._voice_controller.report_error(error.code, str(error))
        except Exception as error:
            self._voice_controller.report_error(
                "microphone_start_failed",
                f"Microphone capture failed to start: {error}",
            )

    def _handle_listen_stop_requested(self, event: Event) -> None:
        del event
        if not self._capture.is_capturing:
            return

        try:
            captured_audio = self._capture.stop()
        except MicrophoneCaptureError as error:
            self._voice_controller.report_error(error.code, str(error))
            return
        except Exception as error:
            self._voice_controller.report_error(
                "microphone_stop_failed",
                f"Microphone capture failed to stop: {error}",
            )
            return

        if self._on_audio_captured is None:
            self._voice_controller.report_error(
                "speech_input_unavailable",
                "Speech recognition is not available yet.",
            )
            return

        callback = self._on_audio_captured
        if self._capture_source == "settings_microphone_test":
            callback = self._on_microphone_test_captured
        self._capture_source = "chat"
        if callback is None:
            self._voice_controller.report_error(
                "speech_input_unavailable",
                "Speech recognition is not available yet.",
            )
            return

        try:
            callback(captured_audio)
        except Exception:
            self._voice_controller.report_error(
                "speech_input_failed",
                "Captured audio could not be submitted for speech recognition.",
            )

    def _handle_listen_cancel_requested(self, event: Event) -> None:
        del event
        self._capture_source = "chat"
        self._capture.cancel()

    def _handle_capture_timeout(self) -> None:
        self._capture_source = "chat"
        self._voice_controller.report_error(
            "capture_timeout",
            "Microphone capture reached its time limit.",
        )

    def _handle_capture_error(self, code: str, message: str) -> None:
        self._capture_source = "chat"
        self._voice_controller.report_error(code, message)

    def _handle_audio_snapshot(self, audio: CapturedAudio) -> None:
        if (
            self._voice_controller.state != VoiceState.LISTENING
            or self._on_audio_snapshot is None
        ):
            return
        self._on_audio_snapshot(audio)

    def _handle_silence(self) -> None:
        if (
            self._capture.is_capturing
            and self._voice_controller.state == VoiceState.LISTENING
        ):
            self._event_bus.publish(
                EventType.VOICE_LISTEN_STOP_REQUESTED,
                {"reason": "silence_detected"},
            )
