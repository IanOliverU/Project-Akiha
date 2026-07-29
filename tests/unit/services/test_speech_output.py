"""Tests for provider-neutral speech output orchestration."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.providers.voice import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceOption,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
)
from project_akiha.services.speech_output import (
    SpeechOutputService,
    SpeechOutputServiceError,
)


class SpeechOutputServiceTest(unittest.TestCase):
    """Verify provider health and failures become stable service errors."""

    def test_returns_provider_audio_with_requested_options(self) -> None:
        provider = _Provider()
        service = SpeechOutputService(provider)

        audio = asyncio.run(
            service.synthesize(
                "Good morning.",
                voice_id="14",
                language="ja-JP",
                speaking_rate=1.2,
            )
        )

        self.assertEqual(audio.data, b"RIFFaudio")
        self.assertEqual(provider.request.voice_id, "14")
        self.assertEqual(provider.request.speaking_rate, 1.2)

    def test_returns_provider_health(self) -> None:
        service = SpeechOutputService(_Provider())

        health = asyncio.run(service.health())

        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)

    def test_returns_discovered_voices(self) -> None:
        service = SpeechOutputService(_Provider())

        voices = tuple(asyncio.run(service.available_voices()))

        self.assertEqual(voices[0].identifier, "14")

    def test_voice_discovery_requires_available_provider(self) -> None:
        service = SpeechOutputService(_Provider(status=VoiceProviderStatus.UNAVAILABLE))

        with self.assertRaises(SpeechOutputServiceError) as captured:
            asyncio.run(service.available_voices())

        self.assertEqual(captured.exception.code, "provider_unavailable")

    def test_unavailable_provider_does_not_receive_text(self) -> None:
        provider = _Provider(status=VoiceProviderStatus.UNAVAILABLE)
        service = SpeechOutputService(provider)

        with self.assertRaises(SpeechOutputServiceError) as captured:
            asyncio.run(service.synthesize("Private response."))

        self.assertEqual(captured.exception.code, "provider_unavailable")
        self.assertIsNone(provider.request)

    def test_preserves_stable_provider_error(self) -> None:
        service = SpeechOutputService(
            _Provider(error=VoiceProviderError("http_failed", "VOICEVOX failed."))
        )

        with self.assertRaises(SpeechOutputServiceError) as captured:
            asyncio.run(service.synthesize("Test."))

        self.assertEqual(captured.exception.code, "http_failed")

    def test_wraps_unexpected_provider_error(self) -> None:
        service = SpeechOutputService(_Provider(error=RuntimeError("connection lost")))

        with self.assertRaises(SpeechOutputServiceError) as captured:
            asyncio.run(service.synthesize("Test."))

        self.assertEqual(captured.exception.code, "synthesis_failed")
        self.assertIn("connection lost", str(captured.exception))

    def test_rejects_invalid_request_before_provider_health_check(self) -> None:
        provider = _Provider()
        service = SpeechOutputService(provider)

        with self.assertRaises(SpeechOutputServiceError) as captured:
            asyncio.run(service.synthesize(" "))

        self.assertEqual(captured.exception.code, "invalid_synthesis_request")
        self.assertFalse(provider.health_called)


class _Provider:
    def __init__(
        self,
        *,
        status: VoiceProviderStatus = VoiceProviderStatus.AVAILABLE,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.health_called = False
        self.request: SpeechSynthesisRequest | None = None

    async def health(self) -> VoiceProviderHealth:
        self.health_called = True
        return VoiceProviderHealth(self.status, "Provider unavailable.")

    async def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> SynthesizedAudio:
        self.request = request
        if self.error is not None:
            raise self.error
        return SynthesizedAudio(b"RIFFaudio")

    async def available_voices(self) -> tuple[VoiceOption, ...]:
        return (VoiceOption("14", "Temporary Japanese voice", "ja-JP"),)


if __name__ == "__main__":
    unittest.main()
