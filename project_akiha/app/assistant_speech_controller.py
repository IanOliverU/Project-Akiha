"""Gate automatic speech for completed assistant replies."""

from __future__ import annotations

import logging
from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.behavior import CompanionMood
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.services.response_segment_renderer import (
    SafeSpeechStyleRenderer,
    SpeechStyleService,
)


class AssistantSpeechController:
    """Send completed assistant text into voice without changing chat data."""

    def __init__(
        self,
        event_bus: EventBus,
        voice_controller: VoiceController,
        config: VoiceConfig,
        *,
        style_service: SpeechStyleService | None = None,
        mood_provider: Callable[[], CompanionMood] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._config = config
        self._mood_provider = mood_provider
        self._style_renderer = SafeSpeechStyleRenderer(
            style_service,
            logger=logger,
        )

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply automatic-speech settings without restarting."""
        self._config = config

    def submit_assistant_reply(self, text: str) -> bool:
        """Request speech for one completed response when policy permits."""
        return self._submit(
            text,
            enabled=self._config.automatic_speech_enabled,
            source="assistant_reply",
        )

    def submit_proactive_suggestion(self, text: str) -> bool:
        """Request speech for one already-approved proactive suggestion."""
        return self._submit(
            text,
            enabled=self._config.proactive_speech_enabled,
            source="proactive_suggestion",
        )

    def submit_pet_reaction(self, text: str) -> bool:
        """Request speech for one explicit, structured pet-care reaction."""
        return self._submit(
            text,
            enabled=self._config.automatic_speech_enabled,
            source="pet_reaction",
        )

    def _submit(self, text: str, *, enabled: bool, source: str) -> bool:
        if (
            not enabled
            or not self._config.output_enabled
            or not isinstance(text, str)
            or not text.strip()
            or self._voice_controller.state != VoiceState.IDLE
            or self._voice_controller.operation != "none"
        ):
            return False

        raw_text = text.strip()
        mood = self._mood_provider() if self._mood_provider is not None else None
        styled = self._style_renderer.render(raw_text, mood)
        self._event_bus.publish(
            EventType.VOICE_SPEAK_REQUESTED,
            {
                "text": styled.text,
                "source": source,
                "speaking_rate_multiplier": styled.speaking_rate_multiplier,
            },
        )
        return True
