"""Coordinate derived output after one canonical response is complete."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CompletedReplySpeech(Protocol):
    """Fallback speech path used when no streaming segment was accepted."""

    def submit_assistant_reply(self, text: str) -> bool:
        """Submit one completed canonical reply for speech."""


class CompletedReplyTranslation(Protocol):
    """Optional subtitle path for completed canonical replies."""

    def translate_assistant_response(self, text: str) -> bool:
        """Request a derived subtitle without rewriting canonical text."""


@dataclass(frozen=True, slots=True)
class ResponseCompletionResult:
    """Derived-output decisions made for one completed canonical response."""

    fallback_speech_submitted: bool
    subtitle_requested: bool


class ResponseCompletionController:
    """Keep completed canonical text separate from derived speech and subtitles."""

    def __init__(
        self,
        speech: CompletedReplySpeech,
        translation: CompletedReplyTranslation,
    ) -> None:
        self._speech = speech
        self._translation = translation

    def complete(
        self,
        canonical_text: str,
        *,
        streaming_speech_started: bool,
    ) -> ResponseCompletionResult:
        """Request only derived output after canonical persistence has completed."""
        if not isinstance(canonical_text, str) or not canonical_text.strip():
            return ResponseCompletionResult(False, False)

        source = canonical_text.strip()
        fallback_speech_submitted = False
        if not streaming_speech_started:
            fallback_speech_submitted = self._speech.submit_assistant_reply(source)
        subtitle_requested = self._translation.translate_assistant_response(source)
        return ResponseCompletionResult(
            fallback_speech_submitted=fallback_speech_submitted,
            subtitle_requested=subtitle_requested,
        )
