"""Provider-neutral text-to-speech orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence

from project_akiha.providers.voice import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceOption,
    VoiceOutputProvider,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
)


class SpeechOutputServiceError(RuntimeError):
    """A privacy-safe speech output service failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code.strip() or "speech_output_error"


class SpeechOutputService:
    """Validate provider health and synthesize one temporary utterance."""

    def __init__(
        self,
        provider: VoiceOutputProvider,
        *,
        readiness_waiter: Callable[[], bool] | None = None,
    ) -> None:
        self._provider = provider
        self._readiness_waiter = readiness_waiter

    async def health(self) -> VoiceProviderHealth:
        """Return provider health without raising connection failures."""
        try:
            return await self._provider.health()
        except Exception as error:
            return VoiceProviderHealth(
                VoiceProviderStatus.UNAVAILABLE,
                f"Speech synthesis health check failed: {error}",
            )

    async def available_voices(self) -> Sequence[VoiceOption]:
        """Return selectable provider voices or a stable diagnostic failure."""
        health = await self.health()
        if health.status != VoiceProviderStatus.AVAILABLE:
            raise SpeechOutputServiceError(
                "provider_unavailable",
                health.detail or "Speech synthesis provider is unavailable.",
            )
        try:
            return await self._provider.available_voices()
        except VoiceProviderError as error:
            raise SpeechOutputServiceError(error.code, str(error)) from error
        except Exception as error:
            raise SpeechOutputServiceError(
                "voice_discovery_failed",
                f"Speech voice discovery failed: {error}",
            ) from error

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
            if self._readiness_waiter is not None:
                try:
                    is_ready = await asyncio.to_thread(self._readiness_waiter)
                except Exception:
                    is_ready = False
                if not is_ready:
                    raise SpeechOutputServiceError(
                        "provider_startup_timeout",
                        "The managed speech engine did not become ready in time.",
                    )
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
