"""Tests for the non-blocking speech synthesis worker."""

from __future__ import annotations

import unittest

from project_akiha.providers.voice import SynthesizedAudio
from project_akiha.services.speech_output import SpeechOutputServiceError
from project_akiha.ui.voice_synthesis_worker import VoiceSynthesisThread


class VoiceSynthesisThreadTest(unittest.TestCase):
    """Verify worker success, failure, and result cancellation."""

    def test_run_emits_audio(self) -> None:
        thread = _thread(_Service())
        audio: list[SynthesizedAudio] = []
        thread.audio_ready.connect(audio.append)

        thread.run()

        self.assertEqual(audio[0].data, b"RIFFaudio")

    def test_run_emits_stable_service_failure(self) -> None:
        thread = _thread(
            _Service(
                error=SpeechOutputServiceError(
                    "provider_unavailable",
                    "Missing.",
                )
            )
        )
        failures: list[tuple[str, str]] = []
        thread.synthesis_failed.connect(
            lambda code, message: failures.append((code, message))
        )

        thread.run()

        self.assertEqual(failures, [("provider_unavailable", "Missing.")])

    def test_cancel_before_run_discards_request(self) -> None:
        service = _Service()
        thread = _thread(service)
        cancelled: list[bool] = []
        thread.synthesis_cancelled.connect(lambda: cancelled.append(True))

        thread.cancel()
        thread.run()

        self.assertEqual(cancelled, [True])
        self.assertFalse(service.called)

    def test_cancel_during_synthesis_discards_audio(self) -> None:
        thread: VoiceSynthesisThread

        def cancel_worker() -> None:
            thread.cancel()

        service = _Service(on_synthesize=cancel_worker)
        thread = _thread(service)
        audio: list[SynthesizedAudio] = []
        cancelled: list[bool] = []
        thread.audio_ready.connect(audio.append)
        thread.synthesis_cancelled.connect(lambda: cancelled.append(True))

        thread.run()

        self.assertEqual(audio, [])
        self.assertEqual(cancelled, [True])


class _Service:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        on_synthesize: object | None = None,
    ) -> None:
        self.error = error
        self.on_synthesize = on_synthesize
        self.called = False

    async def synthesize(
        self,
        text: str,
        *,
        voice_id: str | None,
        language: str,
        speaking_rate: float,
    ) -> SynthesizedAudio:
        del text, voice_id, language, speaking_rate
        self.called = True
        if callable(self.on_synthesize):
            self.on_synthesize()
        if self.error is not None:
            raise self.error
        return SynthesizedAudio(b"RIFFaudio")


def _thread(service: _Service) -> VoiceSynthesisThread:
    return VoiceSynthesisThread(
        service,
        "Good morning.",
        "14",
        "ja-JP",
        1.0,
    )


if __name__ == "__main__":
    unittest.main()
