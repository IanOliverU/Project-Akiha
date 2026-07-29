"""Coordinate synthesized audio playback and voice state."""

from __future__ import annotations

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.providers.voice import (
    AudioPlayback,
    AudioPlaybackError,
    SynthesizedAudio,
)


class VoicePlaybackController:
    """Drive one playback resource without publishing encoded audio."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        playback: AudioPlayback,
    ) -> None:
        self._voice_controller = voice_controller
        self._playback = playback
        event_bus.subscribe(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            self._handle_stop_requested,
        )

    def play(self, audio: SynthesizedAudio) -> None:
        """Begin synthesized audio when an output operation is active."""
        if (
            self._voice_controller.state != VoiceState.THINKING
            or self._voice_controller.operation != "output"
        ):
            self._voice_controller.report_error(
                "unexpected_playback",
                "Synthesized audio arrived without an active speech request.",
            )
            return
        try:
            self._playback.play(
                audio,
                on_started=self._handle_started,
                on_finished=self._handle_finished,
                on_error=self._handle_error,
            )
        except AudioPlaybackError as error:
            self._voice_controller.report_error(error.code, str(error))
        except Exception as error:
            self._voice_controller.report_error(
                "playback_failed",
                f"Speech playback failed: {error}",
            )

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply device and volume settings, stopping current playback."""
        try:
            self._playback.apply_settings(
                config.output_device,
                config.volume_percent,
            )
        except AudioPlaybackError as error:
            self._voice_controller.report_error(error.code, str(error))

    def cancel(self) -> None:
        """Stop playback and release temporary audio during shutdown."""
        self._playback.stop()

    def _handle_stop_requested(self, event: Event) -> None:
        del event
        self._playback.stop()

    def _handle_started(self) -> None:
        self._voice_controller.mark_speaking()

    def _handle_finished(self) -> None:
        if (
            self._voice_controller.state == VoiceState.SPEAKING
            and self._voice_controller.operation == "output"
        ):
            self._voice_controller.recover()

    def _handle_error(self, code: str, message: str) -> None:
        self._voice_controller.report_error(code, message)
