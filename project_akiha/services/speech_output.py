"""Provider-neutral text-to-speech orchestration."""

from __future__ import annotations

from project_akiha.providers.voice import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceOutputProvider,
    VoiceProviderError,
    VoiceProviderStatus,
)


class SpeechOutputServiceError(RuntimeError):
    """A privacy-safe speech output service failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "speech_output_error"


class SpeechOutputService:
    """Validate provider health and synthesize one temporary utterance."""

    def __init__(self, provider: VoiceOutputProvider) -> None:
        self._provider = provider

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None = None,
        language: str = "ja-JP",
        speaking_rate: float = 1.0,
    ) -> SynthesizedAudio:
        """Return encoded speech or a stable diagnostic failure."""
        try:
            request = SpeechSynthesisRequest(
                text=text,
                voice_id=voice_id,
                language=language,
                speaking_rate=speaking_rate,
            )
        except ValueError as error:
            raise SpeechOutputServiceError(
                "invalid_synthesis_request",
                str(error),
            ) from error

        try:
            health = await self._provider.health()
            if health.status != VoiceProviderStatus.AVAILABLE:
                raise SpeechOutputServiceError(
                    "provider_unavailable",
                    health.detail or "Speech synthesis provider is unavailable.",
                )
            return await self._provider.synthesize(request)
        except SpeechOutputServiceError:
            raise
        except VoiceProviderError as error:
            raise SpeechOutputServiceError(error.code, str(error)) from error
        except Exception as error:
            raise SpeechOutputServiceError(
                "synthesis_failed",
                f"Speech synthesis failed: {error}",
            ) from error
