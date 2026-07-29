"""Present voice events on the chat surface without coupling core code to Qt."""

from __future__ import annotations

from typing import Protocol

from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ChatVoiceSurface(Protocol):
    """Chat controls required by the voice event presenter."""

    def set_voice_capabilities(
        self,
        input_enabled: bool,
        output_enabled: bool,
    ) -> None:
        """Update which voice actions are currently configured."""

    def set_voice_state(self, state: str, operation: str = "none") -> None:
        """Present the current voice state."""

    def insert_voice_transcript(self, text: str) -> None:
        """Place recognized text in the editable chat input."""

    def append_error(self, content: str) -> None:
        """Show a visible voice error."""


class ChatVoicePresenter:
    """Validate voice event payloads before updating the chat surface."""

    def __init__(
        self,
        event_bus: EventBus,
        surface: ChatVoiceSurface,
        config: VoiceConfig,
        initial_state: str,
        initial_operation: str = "none",
    ) -> None:
        self._surface = surface

        event_bus.subscribe(
            EventType.VOICE_STATE_CHANGED,
            self._handle_state_changed,
        )
        event_bus.subscribe(
            EventType.VOICE_TRANSCRIPT_READY,
            self._handle_transcript_ready,
        )
        event_bus.subscribe(
            EventType.VOICE_ERROR_OCCURRED,
            self._handle_voice_error,
        )

        self.apply_config(config)
        self._surface.set_voice_state(initial_state, initial_operation)

    def apply_config(self, config: VoiceConfig) -> None:
        """Update chat controls after voice settings change."""
        self._surface.set_voice_capabilities(
            input_enabled=config.input_enabled and config.push_to_talk_enabled,
            output_enabled=config.output_enabled,
        )

    def _handle_state_changed(self, event: Event) -> None:
        state = event.payload.get("state")
        operation = event.payload.get("operation", "none")
        if not isinstance(state, str) or not isinstance(operation, str):
            return
        self._surface.set_voice_state(state, operation)

    def _handle_transcript_ready(self, event: Event) -> None:
        text = event.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return
        self._surface.insert_voice_transcript(text)

    def _handle_voice_error(self, event: Event) -> None:
        message = event.payload.get("message")
        if not isinstance(message, str) or not message.strip():
            message = "Unknown voice error."
        self._surface.append_error(f"Voice: {message}")
