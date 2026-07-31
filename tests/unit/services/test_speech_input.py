"""Tests for local speech input orchestration."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.providers.voice import (
    CapturedAudio,
    VoiceProviderError,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.services.speech_input import (
    SpeechInputService,
    SpeechInputServiceError,
)


class SpeechInputServiceTest(unittest.TestCase):
    """Verify provider health and failures become stable service errors."""

    def test_returns_provider_transcript(self) -> None:
        service = SpeechInputService(_Provider())

        transcript = asyncio.run(service.transcribe(_audio()))

        self.assertEqual(transcript.text, "Recognized text.")

    def test_removes_repeated_echo_wrappers_from_provider_transcript(self) -> None:
        provider = _Provider(
            transcript=VoiceTranscript(
                'I heard you say: I heard you say: "Open Discord."',
                "en",
            )
        )
        service = SpeechInputService(provider)

        transcript = asyncio.run(service.transcribe(_audio()))

        self.assertEqual(transcript.text, "Open Discord.")
        self.assertEqual(transcript.detected_language, "en")

    def test_rejects_transcript_containing_only_echo_wrappers(self) -> None:
        provider = _Provider(transcript=VoiceTranscript("I heard you say:", "en"))
        service = SpeechInputService(provider)

        with self.assertRaises(SpeechInputServiceError) as captured:
            asyncio.run(service.transcribe(_audio()))

        self.assertEqual(captured.exception.code, "empty_transcript")

    def test_preserves_echo_phrase_when_it_is_not_a_leading_wrapper(self) -> None:
        provider = _Provider(
            transcript=VoiceTranscript("Yesterday I heard you say hello.", "en")
        )
        service = SpeechInputService(provider)

        transcript = asyncio.run(service.transcribe(_audio()))

        self.assertEqual(transcript.text, "Yesterday I heard you say hello.")

    def test_unavailable_provider_does_not_receive_audio(self) -> None:
        provider = _Provider(status=VoiceProviderStatus.UNAVAILABLE)
        service = SpeechInputService(provider)

        with self.assertRaises(SpeechInputServiceError) as captured:
            asyncio.run(service.transcribe(_audio()))

        self.assertEqual(captured.exception.code, "provider_unavailable")
        self.assertFalse(provider.transcribe_called)

    def test_preserves_stable_provider_error(self) -> None:
        service = SpeechInputService(
            _Provider(error=VoiceProviderError("model_load_failed", "Missing model."))
        )

        with self.assertRaises(SpeechInputServiceError) as captured:
            asyncio.run(service.transcribe(_audio()))

        self.assertEqual(captured.exception.code, "model_load_failed")


class _Provider:
    def __init__(
        self,
        *,
        status: VoiceProviderStatus = VoiceProviderStatus.AVAILABLE,
        error: Exception | None = None,
        transcript: VoiceTranscript | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.transcript = transcript or VoiceTranscript("Recognized text.", "en")
        self.transcribe_called = False

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(self.status, "Provider unavailable.")

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        del audio
        self.transcribe_called = True
        if self.error is not None:
            raise self.error
        return self.transcript


def _audio() -> CapturedAudio:
    return CapturedAudio(data=b"\x00\x00", sample_rate_hz=16_000)


if __name__ == "__main__":
    unittest.main()
