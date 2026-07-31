"""Tests for provider-neutral voice contracts."""

from __future__ import annotations

import unittest

from project_akiha.providers.voice import (
    CapturedAudio,
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceInputProvider,
    VoiceOption,
    VoiceOutputProvider,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)


class VoiceProviderContractTest(unittest.TestCase):
    """Verify shared voice values reject malformed provider data."""

    def test_models_represent_successful_input_and_output(self) -> None:
        captured = CapturedAudio(
            data=b"\x00\x01",
            sample_rate_hz=16_000,
            language="ja",
        )
        transcript = VoiceTranscript(
            text="おはようございます。",
            detected_language="ja",
        )
        request = SpeechSynthesisRequest(
            text=transcript.text,
            voice_id="14",
            speaking_rate=1.2,
        )
        synthesized = SynthesizedAudio(
            data=b"RIFF-test",
            sample_rate_hz=24_000,
        )
        option = VoiceOption(identifier="14", name="Temporary Japanese voice")
        health = VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

        self.assertEqual(captured.sample_rate_hz, 16_000)
        self.assertEqual(request.language, "ja-JP")
        self.assertEqual(synthesized.media_type, "audio/wav")
        self.assertEqual(option.identifier, "14")
        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)

    def test_provider_health_distinguishes_disabled_and_unavailable(self) -> None:
        disabled = VoiceProviderHealth(
            VoiceProviderStatus.DISABLED,
            "Voice input is disabled.",
        )
        unavailable = VoiceProviderHealth(
            VoiceProviderStatus.UNAVAILABLE,
            "Local model is not installed.",
        )

        self.assertNotEqual(disabled.status, unavailable.status)
        self.assertTrue(unavailable.detail)

    def test_rejects_empty_audio_and_transcript(self) -> None:
        with self.assertRaises(ValueError):
            CapturedAudio(data=b"", sample_rate_hz=16_000)

        with self.assertRaises(ValueError):
            VoiceTranscript(text=" ")

        with self.assertRaisesRegex(ValueError, "between zero and one"):
            VoiceTranscript(text="Speech", confidence=1.1)

    def test_rejects_invalid_synthesis_values(self) -> None:
        with self.assertRaises(ValueError):
            SpeechSynthesisRequest(text="")

        with self.assertRaises(ValueError):
            SpeechSynthesisRequest(text="Test", speaking_rate=3.0)

        with self.assertRaises(ValueError):
            SynthesizedAudio(data=b"")

        with self.assertRaises(ValueError):
            VoiceOption(identifier="", name="Missing identifier")


class _FakeInputProvider:
    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        return VoiceTranscript(text=f"Captured {len(audio.data)} bytes.")

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)


class _FakeOutputProvider:
    async def synthesize(
        self,
        request: SpeechSynthesisRequest,
    ) -> SynthesizedAudio:
        return SynthesizedAudio(data=request.text.encode())

    async def available_voices(self) -> tuple[VoiceOption, ...]:
        return (VoiceOption(identifier="test", name="Test voice"),)

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)


class VoiceProviderProtocolTest(unittest.IsolatedAsyncioTestCase):
    """Verify independent providers can satisfy the shared async contracts."""

    async def test_input_provider_contract(self) -> None:
        provider: VoiceInputProvider = _FakeInputProvider()

        transcript = await provider.transcribe(
            CapturedAudio(data=b"\x00\x01", sample_rate_hz=16_000)
        )
        health = await provider.health()

        self.assertEqual(transcript.text, "Captured 2 bytes.")
        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)

    async def test_output_provider_contract(self) -> None:
        provider: VoiceOutputProvider = _FakeOutputProvider()

        audio = await provider.synthesize(SpeechSynthesisRequest(text="Test"))
        voices = await provider.available_voices()
        health = await provider.health()

        self.assertEqual(audio.data, b"Test")
        self.assertEqual(voices[0].identifier, "test")
        self.assertEqual(health.status, VoiceProviderStatus.AVAILABLE)


if __name__ == "__main__":
    unittest.main()
