"""Coordinate synthesized audio playback and voice state."""

from __future__ import annotations

from collections.abc import Callable

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
        self._recover_on_finish = True
        self._on_finished: Callable[[], None] | None = None
        self._on_error: Callable[[str, str], None] | None = None
        event_bus.subscribe(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            self._handle_stop_requested,
        )

    def play(
        self,
        audio: SynthesizedAudio,
        *,
        recover_on_finish: bool = True,
        on_finished: Callable[[], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ) -> None:
        """Begin synthesized audio when an output operation is active."""
        if (
            self._voice_controller.state
            not in {VoiceState.THINKING, VoiceState.SPEAKING}
            or self._voice_controller.operation != "output"
        ):
            self._voice_controller.report_error(
                "unexpected_playback",
                "Synthesized audio arrived without an active speech request.",
            )
            return
        self._recover_on_finish = recover_on_finish
        self._on_finished = on_finished
        self._on_error = on_error
        try:
            self._playback.play(
                audio,
                on_started=self._handle_started,
                on_finished=self._handle_finished,
                on_error=self._handle_error,
            )
        except AudioPlaybackError as error:
            callback = self._on_error
            self._clear_queue_callbacks()
            if callback is not None:
                callback(error.code, str(error))
            else:
                self._voice_controller.report_error(error.code, str(error))
        except Exception as error:
            callback = self._on_error
            self._clear_queue_callbacks()
            if callback is not None:
                callback("playback_failed", f"Speech playback failed: {error}")
            else:
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
        self._clear_queue_callbacks()

    def _handle_stop_requested(self, event: Event) -> None:
        del event
        self._playback.stop()
        self._clear_queue_callbacks()

    def _handle_started(self) -> None:
        self._voice_controller.mark_speaking()

    def _handle_finished(self) -> None:
        recover_on_finish = self._recover_on_finish
        callback = self._on_finished
        self._clear_queue_callbacks()
        if recover_on_finish and (
            self._voice_controller.state == VoiceState.SPEAKING
            and self._voice_controller.operation == "output"
        ):
            self._voice_controller.recover()
        if callback is not None:
            callback()

    def _handle_error(self, code: str, message: str) -> None:
        callback = self._on_error
        self._clear_queue_callbacks()
        if callback is not None:
            callback(code, message)
        else:
            self._voice_controller.report_error(code, message)

    def _clear_queue_callbacks(self) -> None:
        self._recover_on_finish = True
        self._on_finished = None
        self._on_error = None
