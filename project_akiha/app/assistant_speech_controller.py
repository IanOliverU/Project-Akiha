"""Gate automatic speech for completed assistant replies."""

from __future__ import annotations

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState


class AssistantSpeechController:
    """Send completed assistant text into voice without changing chat data."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        config: VoiceConfig,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._config = config

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply automatic-speech settings without restarting."""
        self._config = config

    def submit_assistant_reply(self, text: str) -> bool:
        """Request speech for one completed response when policy permits."""
        if (
            not self._config.automatic_speech_enabled
            or not self._config.output_enabled
            or not isinstance(text, str)
            or not text.strip()
            or self._voice_controller.state != VoiceState.IDLE
            or self._voice_controller.operation != "none"
        ):
            return False

        self._event_bus.publish(
            EventType.VOICE_SPEAK_REQUESTED,
            {
                "text": text,
                "source": "assistant_reply",
            },
        )
        return True
