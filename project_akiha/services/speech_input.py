"""Local speech-to-text orchestration."""

from __future__ import annotations

from project_akiha.providers.voice import (
    CapturedAudio,
    VoiceInputProvider,
    VoiceProviderError,
    VoiceProviderStatus,
    VoiceTranscript,
)


class SpeechInputServiceError(RuntimeError):
    """A privacy-safe speech input service failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "speech_input_error"


class SpeechInputService:
    """Validate provider health and transcribe one temporary recording."""

    def __init__(self, provider: VoiceInputProvider) -> None:
        self._provider = provider

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        """Return recognized text or a stable diagnostic failure."""
        health = await self._provider.health()
        if health.status != VoiceProviderStatus.AVAILABLE:
            raise SpeechInputServiceError(
                "provider_unavailable",
                health.detail or "Speech recognition provider is unavailable.",
            )

        try:
            return await self._provider.transcribe(audio)
        except VoiceProviderError as error:
            raise SpeechInputServiceError(error.code, str(error)) from error
        except Exception as error:
            raise SpeechInputServiceError(
                "transcription_failed",
                f"Speech recognition failed: {error}",
            ) from error
