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
    MicrophoneActivity,
    MicrophoneCapture,
    MicrophoneCaptureError,
)

_LIVE_TRANSCRIPTION_INTERVAL_SECONDS = 0.6


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
        on_hosted_audio_frame: Callable[[CapturedAudio], None] | None = None,
        on_hosted_audio_ended: Callable[[], None] | None = None,
        on_hosted_audio_failed: Callable[[str, str], None] | None = None,
        schedule_soon: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._capture = capture
        self._config = config
        self._on_audio_captured = on_audio_captured
        self._on_audio_snapshot = on_audio_snapshot
        self._on_microphone_test_captured = on_microphone_test_captured
        self._on_hosted_audio_frame = on_hosted_audio_frame
        self._on_hosted_audio_ended = on_hosted_audio_ended
        self._on_hosted_audio_failed = on_hosted_audio_failed
        self._schedule_soon = schedule_soon or _schedule_soon
        self._capture_source = "chat"
        self._hosted_speech_detected = False

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
        if self._capture_source == "hosted_live":
            input_disabled = not config.enabled or not config.push_to_talk_enabled
        else:
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

    def set_hosted_live_callbacks(
        self,
        *,
        on_audio_frame: Callable[[CapturedAudio], None] | None,
        on_audio_ended: Callable[[], None] | None,
        on_audio_failed: Callable[[str, str], None] | None,
    ) -> None:
        """Set the direct hosted path without changing local STT callbacks."""
        self._on_hosted_audio_frame = on_audio_frame
        self._on_hosted_audio_ended = on_audio_ended
        self._on_hosted_audio_failed = on_audio_failed

    def _handle_listen_requested(self, event: Event) -> None:
        if self._voice_controller.state != VoiceState.LISTENING:
            return
        source = event.payload.get("source")
        self._capture_source = source if isinstance(source, str) else "chat"
        hosted_live = self._capture_source == "hosted_live"
        if hosted_live:
            self._hosted_speech_detected = False

        try:
            self._capture.start(
                timeout_seconds=self._config.capture_timeout_seconds,
                on_timeout=self._handle_capture_timeout,
                on_error=self._handle_capture_error,
                on_audio_frame=(
                    self._handle_hosted_audio_frame if hosted_live else None
                ),
                on_audio_snapshot=(
                    self._handle_audio_snapshot
                    if (
                        not hosted_live
                        and (
                            self._config.live_transcription_enabled
                            or self._config.auto_stop_on_silence_enabled
                        )
                    )
                    else None
                ),
                on_silence=(
                    self._handle_silence
                    if hosted_live or self._config.auto_stop_on_silence_enabled
                    else None
                ),
                on_activity=self._handle_microphone_activity,
                live_interval_seconds=_LIVE_TRANSCRIPTION_INTERVAL_SECONDS,
                silence_timeout_seconds=self._config.silence_timeout_seconds,
                auto_stop_on_silence=(
                    hosted_live or self._config.auto_stop_on_silence_enabled
                ),
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

        capture_source = self._capture_source
        self._capture_source = "chat"
        if capture_source == "hosted_live":
            self._hosted_speech_detected = False
            callback = self._on_hosted_audio_ended
            if callback is None:
                self._voice_controller.report_error(
                    "hosted_live_input_unavailable",
                    "Gemini Live microphone routing is unavailable.",
                )
                return
            try:
                callback()
            except Exception:
                self._voice_controller.report_error(
                    "hosted_live_input_failed",
                    "Gemini Live could not finish the microphone turn.",
                )
            return

        if self._on_audio_captured is None:
            self._voice_controller.report_error(
                "speech_input_unavailable",
                "Speech recognition is not available yet.",
            )
            return

        callback = self._on_audio_captured
        if capture_source == "settings_microphone_test":
            callback = self._on_microphone_test_captured
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
        self._hosted_speech_detected = False
        self._capture.cancel()

    def _handle_capture_timeout(self) -> None:
        capture_source = self._capture_source
        self._capture_source = "chat"
        if capture_source == "hosted_live":
            speech_detected = self._hosted_speech_detected
            self._hosted_speech_detected = False
            if speech_detected:
                callback = self._on_hosted_audio_ended
                if callback is not None:
                    callback()
                    return
            self._schedule_soon(self._renew_hosted_listening)
            return
        self._voice_controller.report_error(
            "capture_timeout",
            "Microphone capture reached its time limit.",
        )

    def _handle_capture_error(self, code: str, message: str) -> None:
        capture_source = self._capture_source
        self._capture_source = "chat"
        self._hosted_speech_detected = False
        if capture_source == "hosted_live":
            callback = self._on_hosted_audio_failed
            if callback is not None:
                callback(code, message)
                return
        self._voice_controller.report_error(code, message)

    def _handle_audio_snapshot(self, audio: CapturedAudio) -> None:
        if (
            self._voice_controller.state != VoiceState.LISTENING
            or self._on_audio_snapshot is None
        ):
            return
        self._on_audio_snapshot(audio)

    def _handle_hosted_audio_frame(self, audio: CapturedAudio) -> None:
        if (
            self._capture_source != "hosted_live"
            or self._voice_controller.state != VoiceState.LISTENING
            or self._on_hosted_audio_frame is None
        ):
            return
        self._on_hosted_audio_frame(audio)

    def _handle_silence(self) -> None:
        if (
            self._capture.is_capturing
            and self._voice_controller.state == VoiceState.LISTENING
        ):
            self._event_bus.publish(
                EventType.VOICE_LISTEN_STOP_REQUESTED,
                {"reason": "silence_detected"},
            )

    def _handle_microphone_activity(self, activity: MicrophoneActivity) -> None:
        if self._voice_controller.state != VoiceState.LISTENING:
            return
        if self._capture_source == "hosted_live" and activity.activity in {
            "speaking",
            "pause",
        }:
            self._hosted_speech_detected = True
        payload: dict[str, object] = {
            "activity": activity.activity,
            "level": activity.level,
        }
        if activity.silence_remaining_seconds is not None:
            payload["silence_remaining_seconds"] = activity.silence_remaining_seconds
        self._event_bus.publish(
            EventType.VOICE_MICROPHONE_ACTIVITY_UPDATED,
            payload,
        )

    def _renew_hosted_listening(self) -> None:
        if (
            self._voice_controller.state is VoiceState.LISTENING
            and not self._capture.is_capturing
        ):
            self._event_bus.publish(
                EventType.VOICE_LISTEN_REQUESTED,
                {"source": "hosted_live", "reason": "idle_window_renewed"},
            )


def _schedule_soon(callback: Callable[[], None]) -> None:
    from PySide6.QtCore import QTimer

    QTimer.singleShot(0, callback)
