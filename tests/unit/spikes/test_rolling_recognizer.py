"""Tests for rolling transcript revisions over bounded PCM frames."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator

from project_akiha.providers.voice import (
    CapturedAudio,
    VoiceProviderHealth,
    VoiceProviderStatus,
    VoiceTranscript,
)
from project_akiha.services.speech_input import SpeechInputService
from spikes.voice_pipeline.pipeline_spike import PipelineSpike, ResponseSegment
from spikes.voice_pipeline.qt_audio_bridge import AudioFrame
from spikes.voice_pipeline.rolling_recognizer import RollingTranscriptRecognizer


class RollingTranscriptRecognizerTest(unittest.TestCase):
    def test_revisions_flow_through_pipeline_with_final_only_commit(self) -> None:
        async def exercise() -> None:
            provider = _Provider(
                (
                    VoiceTranscript("Open Spotify", "en", 0.8),
                    VoiceTranscript("Akiha, open Spotify please.", "en", 0.9),
                )
            )
            recognizer = _recognizer(provider)
            intent = _IntentProbe()
            playback = _Playback()
            pipeline = PipelineSpike()
            pipeline.start()

            response = await pipeline.run_turn(
                _frame_stream(_frames(6)),
                recognizer,
                intent,
                _Responder(),
                _Synthesizer(),
                playback,
            )

            self.assertEqual(intent.prepared, ["Open Spotify"])
            self.assertEqual(intent.committed, ["Akiha, open Spotify please."])
            self.assertEqual(response, "Spotify was started.")
            self.assertEqual(playback.texts, ["Spotify was started."])

        asyncio.run(exercise())

    def test_emits_stable_partials_and_one_authoritative_final(self) -> None:
        async def exercise() -> None:
            provider = _Provider(
                (
                    VoiceTranscript("Open", "en", 0.7),
                    VoiceTranscript("Open Spotify", "en", 0.8),
                    VoiceTranscript("Akiha, open Spotify please.", "en", 0.9),
                )
            )
            recognizer = _recognizer(provider)
            revisions = []

            for frame in _frames(12):
                revision = await recognizer.accept(frame)
                if revision is not None:
                    revisions.append(revision)
            final = await recognizer.finalize()

            self.assertEqual(
                [item.text for item in revisions], ["Open", "Open Spotify"]
            )
            self.assertEqual([item.revision for item in revisions], [1, 2])
            self.assertFalse(any(item.is_final for item in revisions))
            self.assertEqual(final.text, "Akiha, open Spotify please.")
            self.assertEqual(final.revision, 3)
            self.assertTrue(final.is_final)
            self.assertEqual(final.detected_language, "en")
            self.assertEqual(final.confidence, 0.9)
            self.assertEqual(provider.audio_lengths, [19_200, 38_400, 38_400])
            self.assertFalse(recognizer.is_active)

        asyncio.run(exercise())

    def test_suppresses_duplicate_and_one_off_disruptive_partial(self) -> None:
        async def exercise() -> None:
            provider = _Provider(
                (
                    VoiceTranscript("Open Chrome"),
                    VoiceTranscript("Open Chrome"),
                    VoiceTranscript("Start Discord"),
                    VoiceTranscript("Open Chrome please"),
                    VoiceTranscript("Open Chrome please"),
                )
            )
            recognizer = _recognizer(provider)
            partials = []

            for frame in _frames(24):
                revision = await recognizer.accept(frame)
                if revision is not None:
                    partials.append(revision.text)
            await recognizer.finalize()

            self.assertEqual(partials, ["Open Chrome", "Open Chrome please"])

        asyncio.run(exercise())

    def test_rejects_wrong_turn_sequence_format_and_utterance_overflow(self) -> None:
        async def exercise() -> None:
            recognizer = _recognizer(_Provider((VoiceTranscript("unused"),)))

            with self.assertRaisesRegex(ValueError, "different recognition turn"):
                await recognizer.accept(_frame(1, turn_id=2))
            with self.assertRaisesRegex(ValueError, "accepted in sequence"):
                await recognizer.accept(_frame(2))
            with self.assertRaisesRegex(ValueError, "format changed"):
                await recognizer.accept(_frame(1, sample_rate_hz=48_000))

            recognizer.cancel()
            bounded = RollingTranscriptRecognizer(
                SpeechInputService(_Provider((VoiceTranscript("unused"),))),
                partial_interval_seconds=0.1,
                maximum_utterance_seconds=0.1,
            )
            bounded.start(
                session_id="session-1",
                turn_id=1,
                sample_rate_hz=16_000,
                channels=1,
                sample_width_bytes=2,
            )
            with self.assertRaisesRegex(ValueError, "utterance limit"):
                await bounded.accept(_frame(1, data=bytes(3_202)))

        asyncio.run(exercise())

    def test_cancel_discards_audio_and_prevents_finalization(self) -> None:
        async def exercise() -> None:
            provider = _Provider((VoiceTranscript("unused"),))
            recognizer = _recognizer(provider)
            await recognizer.accept(_frame(1))

            recognizer.cancel()

            self.assertFalse(recognizer.is_active)
            with self.assertRaisesRegex(RuntimeError, "no active turn"):
                await recognizer.finalize()
            self.assertEqual(provider.audio_lengths, [])

        asyncio.run(exercise())


class _Provider:
    def __init__(self, transcripts: tuple[VoiceTranscript, ...]) -> None:
        self._transcripts = iter(transcripts)
        self.audio_lengths: list[int] = []

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def transcribe(self, audio: CapturedAudio) -> VoiceTranscript:
        self.audio_lengths.append(len(audio.data))
        return next(self._transcripts)


class _IntentProbe:
    def __init__(self) -> None:
        self.prepared: list[str] = []
        self.committed: list[str] = []

    def prepare(self, text: str) -> None:
        self.prepared.append(text)

    def commit(self, text: str) -> None:
        self.committed.append(text)


class _Responder:
    async def stream(self, text: str) -> AsyncIterator[str]:
        self.received = text
        yield "Spotify was started."


class _Synthesizer:
    async def synthesize(self, segment: ResponseSegment) -> bytes:
        return segment.text.encode("utf-8")


class _Playback:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def play(self, segment: ResponseSegment, audio: bytes) -> None:
        del segment
        self.texts.append(audio.decode("utf-8"))


def _recognizer(provider: _Provider) -> RollingTranscriptRecognizer:
    recognizer = RollingTranscriptRecognizer(SpeechInputService(provider))
    recognizer.start(
        session_id="session-1",
        turn_id=1,
        sample_rate_hz=16_000,
        channels=1,
        sample_width_bytes=2,
        language="auto",
    )
    return recognizer


def _frames(count: int) -> tuple[AudioFrame, ...]:
    return tuple(_frame(index) for index in range(1, count + 1))


async def _frame_stream(frames: tuple[AudioFrame, ...]) -> AsyncIterator[AudioFrame]:
    for frame in frames:
        await asyncio.sleep(0)
        yield frame


def _frame(
    sequence: int,
    *,
    turn_id: int = 1,
    sample_rate_hz: int = 16_000,
    data: bytes | None = None,
) -> AudioFrame:
    return AudioFrame(
        session_id="session-1",
        turn_id=turn_id,
        sequence=sequence,
        captured_at_ns=sequence,
        data=data if data is not None else bytes(3_200),
        sample_rate_hz=sample_rate_hz,
        channels=1,
        sample_width_bytes=2,
    )


if __name__ == "__main__":
    unittest.main()
