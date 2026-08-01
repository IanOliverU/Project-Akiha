"""Render canonical response segments into safe speech-only derivatives."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from project_akiha.core.behavior import CompanionMood
from project_akiha.core.voice_session import (
    CanonicalResponseSegment,
    ResponseSegment,
)
from project_akiha.services.speech_identity import (
    AkihaSpeechStyleService,
    StyledSpeech,
)


class SpeechStyleService(Protocol):
    """Speech-only transformation independent from synthesis providers."""

    def style(
        self,
        text: str,
        mood: CompanionMood | None = None,
    ) -> StyledSpeech:
        """Return a spoken rendering without mutating canonical text."""


class SafeSpeechStyleRenderer:
    """Validate identity output and fall back without logging private text."""

    def __init__(
        self,
        style_service: SpeechStyleService | None = None,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._style_service = style_service or AkihaSpeechStyleService()
        self._logger = logger or logging.getLogger("project_akiha.voice.identity")

    def render(
        self,
        canonical_text: str,
        mood: CompanionMood | None = None,
    ) -> StyledSpeech:
        """Return validated speech identity or the untouched canonical text."""
        raw_text = canonical_text.strip()
        if not raw_text:
            raise ValueError("Speech rendering requires non-empty canonical text.")

        try:
            styled = self._style_service.style(raw_text, mood)
        except Exception as error:
            self._log_fallback(type(error).__name__)
            return StyledSpeech(raw_text)

        if not _is_valid_styled_speech(styled):
            self._log_fallback("invalid_result")
            return StyledSpeech(raw_text)
        return StyledSpeech(
            styled.text.strip(),
            float(styled.speaking_rate_multiplier),
        )

    def _log_fallback(self, reason: str) -> None:
        self._logger.warning(
            "Speech identity styling fell back to canonical text (%s).",
            reason,
        )


class ResponseSegmentRenderer:
    """Attach Akiha's speech identity to immutable canonical segments."""

    def __init__(
        self,
        style_renderer: SafeSpeechStyleRenderer | None = None,
        *,
        mood_provider: Callable[[], CompanionMood] | None = None,
    ) -> None:
        self._style_renderer = style_renderer or SafeSpeechStyleRenderer()
        self._mood_provider = mood_provider

    def render(self, segment: CanonicalResponseSegment) -> ResponseSegment:
        """Create one synthesis-ready derivative preserving segment identity."""
        mood = self._mood_provider() if self._mood_provider is not None else None
        styled = self._style_renderer.render(segment.canonical_text, mood)
        return ResponseSegment(
            response_id=segment.response_id,
            segment_index=segment.segment_index,
            canonical_text=segment.canonical_text,
            speech_text=styled.text,
            speaking_rate_multiplier=styled.speaking_rate_multiplier,
            is_final=segment.is_final,
        )


def canonical_speech_fallback(segment: CanonicalResponseSegment) -> ResponseSegment:
    """Return a synthesis-ready canonical fallback for an infrastructure error."""
    return ResponseSegment(
        response_id=segment.response_id,
        segment_index=segment.segment_index,
        canonical_text=segment.canonical_text,
        speech_text=segment.canonical_text,
        is_final=segment.is_final,
    )


def _is_valid_styled_speech(styled: object) -> bool:
    return (
        isinstance(styled, StyledSpeech)
        and isinstance(styled.text, str)
        and bool(styled.text.strip())
        and not isinstance(styled.speaking_rate_multiplier, bool)
        and isinstance(styled.speaking_rate_multiplier, (int, float))
        and 0.5 <= styled.speaking_rate_multiplier <= 1.5
    )
