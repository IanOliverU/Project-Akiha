"""Gate automatic speech for completed assistant replies."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from project_akiha.app.voice_controller import VoiceController
from project_akiha.config import VoiceConfig
from project_akiha.core.behavior import CompanionMood
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.services.speech_identity import (
    AkihaSpeechStyleService,
    StyledSpeech,
)


class SpeechStyleService(Protocol):
    """Speech-only transformation contract independent from TTS providers."""

    def style(
        self,
        text: str,
        mood: CompanionMood | None = None,
    ) -> StyledSpeech:
        """Return a safe spoken rendering of one completed reply."""


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
        self._style_service = style_service or AkihaSpeechStyleService()
        self._mood_provider = mood_provider
        self._logger = logger or logging.getLogger("project_akiha.voice.identity")

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

        raw_text = text.strip()
        styled = self._style_reply(raw_text)
        self._event_bus.publish(
            EventType.VOICE_SPEAK_REQUESTED,
            {
                "text": styled.text,
                "source": "assistant_reply",
                "speaking_rate_multiplier": styled.speaking_rate_multiplier,
            },
        )
        return True

    def _style_reply(self, raw_text: str) -> StyledSpeech:
        try:
            mood = self._mood_provider() if self._mood_provider is not None else None
            styled = self._style_service.style(raw_text, mood)
        except Exception as error:
            self._log_fallback(type(error).__name__)
            return StyledSpeech(raw_text)

        if (
            not isinstance(styled, StyledSpeech)
            or not isinstance(styled.text, str)
            or not styled.text.strip()
            or isinstance(styled.speaking_rate_multiplier, bool)
            or not isinstance(styled.speaking_rate_multiplier, (int, float))
            or not 0.5 <= styled.speaking_rate_multiplier <= 1.5
        ):
            self._log_fallback("invalid_result")
            return StyledSpeech(raw_text)
        return StyledSpeech(
            styled.text.strip(),
            float(styled.speaking_rate_multiplier),
        )

    def _log_fallback(self, reason: str) -> None:
        self._logger.warning(
            "Speech identity styling fell back to the original reply (%s).",
            reason,
        )
