"""Explicit fallback providers for unavailable voice capabilities."""

from __future__ import annotations

from collections.abc import Sequence

from project_akiha.providers.voice.base import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceOption,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
)


class UnavailableVoiceOutputProvider:
    """Report that speech synthesis has no usable backend."""

    def __init__(
        self,
        detail: str = "Speech synthesis provider is unavailable.",
    ) -> None:
        self._detail = detail.strip() or "Speech synthesis provider is unavailable."

    async def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> SynthesizedAudio:
        """Reject synthesis without retaining the requested text."""
        del request
        raise VoiceProviderError("provider_unavailable", self._detail)

    async def available_voices(self) -> Sequence[VoiceOption]:
        """Return no voices while the backend is unavailable."""
        return ()

    async def health(self) -> VoiceProviderHealth:
        """Return an explicit unavailable health result."""
        return VoiceProviderHealth(VoiceProviderStatus.UNAVAILABLE, self._detail)
