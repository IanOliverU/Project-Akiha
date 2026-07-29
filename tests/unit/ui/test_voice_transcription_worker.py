"""Tests for the non-blocking speech recognition worker."""

from __future__ import annotations

import unittest

from project_akiha.providers.voice import CapturedAudio, VoiceTranscript
from project_akiha.services.speech_input import SpeechInputServiceError
from project_akiha.ui.voice_transcription_worker import VoiceTranscriptionThread


class VoiceTranscriptionThreadTest(unittest.TestCase):
    """Verify worker success, failure, and result cancellation."""

    def test_run_emits_transcript(self) -> None:
        thread = VoiceTranscriptionThread(_Service(), _audio())
        transcripts: list[VoiceTranscript] = []
        thread.transcript_ready.connect(transcripts.append)

        thread.run()

        self.assertEqual(transcripts[0].text, "Recognized.")

    def test_run_emits_stable_service_failure(self) -> None:
        thread = VoiceTranscriptionThread(
            _Service(error=SpeechInputServiceError("provider_unavailable", "Missing.")),
            _audio(),
        )
        failures: list[tuple[str, str]] = []
        thread.transcription_failed.connect(
            lambda code, message: failures.append((code, message))
        )

        thread.run()

        self.assertEqual(failures, [("provider_unavailable", "Missing.")])

    def test_cancel_before_run_discards_audio(self) -> None:
        service = _Service()
        thread = VoiceTranscriptionThread(service, _audio())
        cancelled: list[bool] = []
        thread.transcription_cancelled.connect(lambda: cancelled.append(True))

        thread.cancel()
        thread.run()

        self.assertEqual(cancelled, [True])
        self.assertFalse(service.called)

    def test_cancel_during_transcription_discards_result(self) -> None:
        thread: VoiceTranscriptionThread

        def cancel_worker() -> None:
            thread.cancel()

        service = _Service(on_transcribe=cancel_worker)
        thread = VoiceTranscriptionThread(service, _audio())
        transcripts: list[VoiceTranscript] = []
        cancelled: list[bool] = []
        thread.transcript_ready.connect(transcripts.append)
        thread.transcription_cancelled.connect(lambda: cancelled.append(True))

        thread.run()

        self.assertEqual(transcripts, [])
        self.assertEqual(cancelled, [True])


class _Service:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        on_transcribe: object | None = None,
    ) -> None:
        self.error = error
        self.on_transcribe = on_transcribe
        self.called = False

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        del audio
        self.called = True
        if callable(self.on_transcribe):
            self.on_transcribe()
        if self.error is not None:
            raise self.error
        return VoiceTranscript("Recognized.", "en")


def _audio() -> CapturedAudio:
    return CapturedAudio(data=b"\x00\x00", sample_rate_hz=16_000)


if __name__ == "__main__":
    unittest.main()
