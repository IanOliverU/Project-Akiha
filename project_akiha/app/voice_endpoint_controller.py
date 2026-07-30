"""Stop microphone capture after recognized speech stops progressing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QTimer

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState


class _TimerSignal(Protocol):
    def connect(self, handler: Callable[[], None]) -> None:
        """Connect one timeout callback."""


class _EndpointTimer(Protocol):
    timeout: _TimerSignal

    def setSingleShot(self, single_shot: bool) -> None:
        """Configure one-shot behavior."""

    def start(self, milliseconds: int) -> None:
        """Start or restart the timer."""

    def stop(self) -> None:
        """Stop the timer."""


class VoiceEndpointController:
    """Use live transcript progress as a fan-resistant speech endpoint."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        config: VoiceConfig,
        *,
        timer_factory: Callable[[], _EndpointTimer] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._config = config
        self._timer = (timer_factory or QTimer)()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._handle_timeout)
        self._last_progress = ""
        self._armed = False

        event_bus.subscribe(
            EventType.VOICE_LISTEN_REQUESTED,
            self._handle_listen_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            self._handle_listen_ended,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_listen_ended,
        )
        event_bus.subscribe(
            EventType.VOICE_TRANSCRIPT_PARTIAL,
            self._handle_transcript_partial,
        )
        event_bus.subscribe(
            EventType.VOICE_STATE_CHANGED,
            self._handle_state_changed,
        )

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply endpoint timing changes without restarting Akiha."""
        self._config = config
        if not config.auto_stop_on_silence_enabled:
            self.cancel()

    def cancel(self) -> None:
        """Disarm transcript-based endpoint detection."""
        self._timer.stop()
        self._last_progress = ""
        self._armed = False

    def _handle_listen_requested(self, event: Event) -> None:
        del event
        self.cancel()

    def _handle_listen_ended(self, event: Event) -> None:
        del event
        self.cancel()

    def _handle_transcript_partial(self, event: Event) -> None:
        if (
            not self._config.auto_stop_on_silence_enabled
            or self._voice_controller.state != VoiceState.LISTENING
            or self._voice_controller.operation != "input"
        ):
            return
        text = event.payload.get("text")
        if not isinstance(text, str):
            return
        progress = " ".join(text.casefold().split())
        if not progress:
            return
        if self._last_progress and len(progress) <= len(self._last_progress):
            return

        self._last_progress = progress
        self._armed = True
        self._timer.start(round(self._config.silence_timeout_seconds * 1000))

    def _handle_state_changed(self, event: Event) -> None:
        state = event.payload.get("state")
        operation = event.payload.get("operation")
        if state != VoiceState.LISTENING.value or operation != "input":
            self.cancel()

    def _handle_timeout(self) -> None:
        if (
            self._armed
            and self._voice_controller.state == VoiceState.LISTENING
            and self._voice_controller.operation == "input"
        ):
            self._event_bus.publish(
                EventType.VOICE_LISTEN_STOP_REQUESTED,
                {"reason": "transcript_inactivity"},
            )
        self.cancel()
