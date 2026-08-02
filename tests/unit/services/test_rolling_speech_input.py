"""Tests for bounded rolling recognition over faster-whisper."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.core.voice_session import (
    AudioFrame,
    EndpointReason,
    TranscriptConfidence,
    TranscriptStatus,
    VoiceCancellationToken,
)
from project_akiha.providers.voice import (
    CapturedAudio,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.services.rolling_speech_input import (
    RollingFasterWhisperAdapter,
    RollingFasterWhisperRecognizer,
)
from project_akiha.services.speech_input import SpeechInputService


class RollingFasterWhisperAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_requests_overlapping_recent_windows_on_cadence(self) -> None:
        provider = _Provider(
            VoiceTranscript("Open", "en", 0.7),
            VoiceTranscript("Open Spotify", "en", 0.8),
        )
        adapter = _adapter(provider)

        results = []
        for sequence in range(4):
            result = await adapter.accept_audio(_frame(sequence))
            if result is not None:
                results.append(result)

        self.assertEqual(provider.audio_lengths, [40, 60])
        self.assertEqual(
            [result.transcript.text for result in results],
            ["Open", "Open Spotify"],
        )
        self.assertEqual(results[-1].first_frame_sequence, 1)
        self.assertEqual(results[-1].last_frame_sequence, 3)

    async def test_final_uses_bounded_utterance_and_releases_state(self) -> None:
        provider = _Provider(
            VoiceTranscript("partial"),
            VoiceTranscript("partial two"),
            VoiceTranscript("partial three"),
            VoiceTranscript("Final command", "en", 0.9),
        )
        adapter = _adapter(provider)
        for sequence in range(6):
            await adapter.accept_audio(_frame(sequence))

        final = await adapter.finalize(EndpointReason.SILENCE)

        self.assertTrue(final.is_final)
        self.assertEqual(final.endpoint_reason, EndpointReason.SILENCE)
        self.assertEqual(final.transcript.text, "Final command")
        self.assertEqual(provider.audio_lengths, [40, 60, 60, 100])
        self.assertEqual(final.first_frame_sequence, 1)
        self.assertEqual(final.last_frame_sequence, 5)
        self.assertFalse(adapter.is_active)

    async def test_buffered_final_audio_skips_partial_inference(self) -> None:
        provider = _Provider(VoiceTranscript("Final command", "en", 0.9))
        adapter = _adapter(provider)

        for sequence in range(4):
            adapter.buffer_audio(_frame(sequence))
        final = await adapter.finalize(EndpointReason.SILENCE)

        self.assertEqual(final.transcript.text, "Final command")
        self.assertEqual(provider.audio_lengths, [80])

    async def test_empty_partial_is_suppressed_then_recovers(self) -> None:
        provider = _ProviderErrorThenTranscript(VoiceTranscript("Recovered", "en"))
        adapter = _adapter(provider)

        self.assertIsNone(await adapter.accept_audio(_frame(0)))
        self.assertIsNone(await adapter.accept_audio(_frame(1)))
        self.assertIsNone(await adapter.accept_audio(_frame(2)))
        recovered = await adapter.accept_audio(_frame(3))

        self.assertIsNotNone(recovered)
        assert recovered is not None
        self.assertEqual(recovered.transcript.text, "Recovered")

    async def test_cancellation_discards_late_provider_result(self) -> None:
        provider = _BlockingProvider()
        token = VoiceCancellationToken()
        adapter = _adapter(provider, token=token)
        self.assertIsNone(await adapter.accept_audio(_frame(0)))
        task = asyncio.create_task(adapter.accept_audio(_frame(1)))
        await asyncio.wait_for(provider.started.wait(), timeout=1.0)

        adapter.cancel()
        provider.release.set()

        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(adapter.is_active)

    async def test_rejects_wrong_turn_and_out_of_order_frame(self) -> None:
        adapter = _adapter(_Provider(VoiceTranscript("unused")))
        with self.assertRaisesRegex(ValueError, "different recognition turn"):
            await adapter.accept_audio(_frame(0, turn_id="turn-2"))

        adapter.cancel()
        adapter = _adapter(_Provider(VoiceTranscript("unused")))
        with self.assertRaisesRegex(ValueError, "accepted in sequence"):
            await adapter.accept_audio(_frame(1))


class RollingFasterWhisperRecognizerTest(unittest.IsolatedAsyncioTestCase):
    async def test_emits_ordered_partials_and_one_authoritative_final(self) -> None:
        provider = _Provider(
            VoiceTranscript("Open", "en", 0.2),
            VoiceTranscript("Open Spotify", "en", 0.8),
            VoiceTranscript("Akiha, open Spotify please", "en", 0.5),
        )
        revisions = []
        recognizer = _recognizer(provider, revisions.append)

        for sequence in range(4):
            await recognizer.accept_audio(_frame(sequence))
        await recognizer.finalize(EndpointReason.SILENCE)

        self.assertEqual(
            [revision.text for revision in revisions],
            ["Open", "Open Spotify", "Akiha, open Spotify please"],
        )
        self.assertEqual(
            [revision.revision_number for revision in revisions],
            [0, 1, 2],
        )
        self.assertEqual(
            [revision.status for revision in revisions],
            [
                TranscriptStatus.PARTIAL,
                TranscriptStatus.PARTIAL,
                TranscriptStatus.FINAL,
            ],
        )
        self.assertEqual(
            [revision.confidence for revision in revisions],
            [
                TranscriptConfidence.LOW,
                TranscriptConfidence.HIGH,
                TranscriptConfidence.MEDIUM,
            ],
        )
        self.assertEqual(revisions[-1].endpoint_reason, EndpointReason.SILENCE)
        self.assertFalse(recognizer.is_active)
        with self.assertRaisesRegex(RuntimeError, "does not own"):
            await recognizer.finalize(EndpointReason.MANUAL_STOP)
        self.assertEqual(len(revisions), 3)

    async def test_suppresses_duplicate_regression_and_one_off_rewrite(self) -> None:
        provider = _Provider(
            VoiceTranscript("Open Spotify"),
            VoiceTranscript("Open Spotify"),
            VoiceTranscript("Open"),
            VoiceTranscript("Start Discord"),
            VoiceTranscript("Start Discord now"),
        )
        revisions = []
        recognizer = _recognizer(provider, revisions.append)

        for sequence in range(10):
            await recognizer.accept_audio(_frame(sequence))

        self.assertEqual(
            [revision.text for revision in revisions],
            ["Open Spotify", "Start Discord now"],
        )
        self.assertTrue(
            all(revision.status is TranscriptStatus.PARTIAL for revision in revisions)
        )
        recognizer.cancel()

    async def test_final_is_revision_zero_when_no_partial_was_ready(self) -> None:
        revisions = []
        recognizer = _recognizer(
            _Provider(VoiceTranscript("Final only", "en", None)),
            revisions.append,
        )

        await recognizer.accept_audio(_frame(0))
        await recognizer.finalize(EndpointReason.MANUAL_STOP)

        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].revision_number, 0)
        self.assertEqual(revisions[0].status, TranscriptStatus.FINAL)
        self.assertEqual(revisions[0].confidence, TranscriptConfidence.UNKNOWN)
        self.assertEqual(revisions[0].endpoint_reason, EndpointReason.MANUAL_STOP)


class _Provider:
    def __init__(self, *transcripts: VoiceTranscript) -> None:
        self._transcripts = iter(transcripts)
        self.audio_lengths: list[int] = []

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        self.audio_lengths.append(len(audio.data))
        return next(self._transcripts)


class _ProviderErrorThenTranscript(_Provider):
    def __init__(self, transcript: VoiceTranscript) -> None:
        super().__init__(transcript)
        self._failed = False

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        if not self._failed:
            self._failed = True
            from project_akiha.providers.voice import VoiceProviderError

            raise VoiceProviderError("empty_transcript", "No speech recognized.")
        return await super().transcribe(audio)


class _BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        del audio
        self.started.set()
        await self.release.wait()
        return VoiceTranscript("Late result", "en")


def _adapter(
    provider: object,
    *,
    token: VoiceCancellationToken | None = None,
) -> RollingFasterWhisperAdapter:
    adapter = RollingFasterWhisperAdapter(
        SpeechInputService(provider),  # type: ignore[arg-type]
        partial_interval_seconds=0.2,
        partial_window_seconds=0.3,
        maximum_utterance_seconds=0.5,
    )
    adapter.start_turn(
        session_id="session-1",
        turn_id="turn-1",
        cancellation_token=token or VoiceCancellationToken(),
        language="auto",
    )
    return adapter


def _recognizer(provider: object, on_revision) -> RollingFasterWhisperRecognizer:
    adapter = RollingFasterWhisperAdapter(
        SpeechInputService(provider),  # type: ignore[arg-type]
        partial_interval_seconds=0.2,
        partial_window_seconds=0.3,
        maximum_utterance_seconds=0.5,
    )
    recognizer = RollingFasterWhisperRecognizer(adapter, language="auto")
    recognizer.start_turn(
        "session-1",
        "turn-1",
        on_revision,
        VoiceCancellationToken(),
    )
    return recognizer


def _frame(sequence: int, *, turn_id: str = "turn-1") -> AudioFrame:
    return AudioFrame(
        session_id="session-1",
        turn_id=turn_id,
        sequence_number=sequence,
        captured_at_monotonic=float(sequence),
        sample_rate_hz=100,
        channels=1,
        sample_width_bytes=2,
        data=bytes(20),
    )


if __name__ == "__main__":
    unittest.main()
