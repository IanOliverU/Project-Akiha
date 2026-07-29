"""Tests for explicit unavailable voice providers."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.providers.voice import (
    SpeechSynthesisRequest,
    UnavailableVoiceOutputProvider,
    VoiceProviderError,
    VoiceProviderStatus,
)


class UnavailableVoiceOutputProviderTest(unittest.TestCase):
    """Verify the fallback exposes no accidental synthesis path."""

    def test_health_reports_unavailable_detail(self) -> None:
        provider = UnavailableVoiceOutputProvider("VOICEVOX is offline.")

        health = asyncio.run(provider.health())

        self.assertEqual(health.status, VoiceProviderStatus.UNAVAILABLE)
        self.assertEqual(health.detail, "VOICEVOX is offline.")

    def test_synthesis_raises_stable_provider_error(self) -> None:
        provider = UnavailableVoiceOutputProvider("VOICEVOX is offline.")

        with self.assertRaises(VoiceProviderError) as captured:
            asyncio.run(provider.synthesize(SpeechSynthesisRequest("Test.")))

        self.assertEqual(captured.exception.code, "provider_unavailable")

    def test_no_voices_are_available(self) -> None:
        provider = UnavailableVoiceOutputProvider()

        self.assertEqual(tuple(asyncio.run(provider.available_voices())), ())


if __name__ == "__main__":
    unittest.main()
