"""Tests for the ordered concurrent VOICEVOX processor prototype."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.providers.voice import (
    SpeechSynthesisRequest,
    SynthesizedAudio,
    VoiceProviderHealth,
    VoiceProviderStatus,
)
from project_akiha.services.speech_output import SpeechOutputService
from spikes.voice_pipeline.pipeline_spike import ResponseSegment
from spikes.voice_pipeline.voicevox_processor import OrderedVoiceVoxProcessor


class OrderedVoiceVoxProcessorTest(unittest.TestCase):
    def test_overlaps_synthesis_and_preserves_playback_order(self) -> None:
        async def exercise() -> None:
            provider = _ControlledProvider()
            playback = _Playback()
            processor = OrderedVoiceVoxProcessor(
                SpeechOutputService(provider),
                voice_id="10",
                speaking_rate=0.9,
                maximum_concurrent_synthesis=2,
            )
            processor.start_turn(1, playback)
            processor.submit(_segment(0, "First sentence."))
            processor.submit(_segment(1, "Second sentence."))

            await asyncio.wait_for(provider.both_started.wait(), timeout=1.0)
            provider.release_second.set()
            await asyncio.sleep(0)
            self.assertEqual(playback.indices, [])
            provider.release_first.set()
            await processor.finish_turn(1)

            self.assertEqual(playback.indices, [0, 1])
            self.assertEqual(playback.texts, ["First sentence.", "Second sentence."])
            self.assertEqual(
                [request.voice_id for request in provider.requests], ["10", "10"]
            )
            self.assertTrue(
                all(request.speaking_rate == 0.9 for request in provider.requests)
            )
            self.assertFalse(processor.is_active)

        asyncio.run(exercise())

    def test_cancellation_discards_late_synthesis_and_playback(self) -> None:
        async def exercise() -> None:
            provider = _BlockingProvider()
            playback = _Playback()
            processor = OrderedVoiceVoxProcessor(SpeechOutputService(provider))
            processor.start_turn(7, playback)
            processor.submit(_segment(0, "Do not play this.", turn_id=7))
            await asyncio.wait_for(provider.started.wait(), timeout=1.0)

            cancelled = await processor.cancel_turn(7)
            provider.release.set()
            await asyncio.sleep(0)

            self.assertTrue(cancelled)
            self.assertEqual(playback.indices, [])
            self.assertFalse(processor.is_active)
            self.assertFalse(await processor.cancel_turn(7))

        asyncio.run(exercise())

    def test_rejects_wrong_turn_and_out_of_order_segments(self) -> None:
        async def exercise() -> None:
            processor = OrderedVoiceVoxProcessor(
                SpeechOutputService(_ImmediateProvider())
            )
            processor.start_turn(2, _Playback())

            with self.assertRaisesRegex(ValueError, "different turn"):
                processor.submit(_segment(0, "Wrong.", turn_id=3))
            with self.assertRaisesRegex(ValueError, "submitted in order"):
                processor.submit(_segment(1, "Second.", turn_id=2))

            await processor.cancel_turn(2)

        asyncio.run(exercise())

    def test_provider_failure_cleans_up_turn(self) -> None:
        async def exercise() -> None:
            processor = OrderedVoiceVoxProcessor(
                SpeechOutputService(_FailingProvider())
            )
            processor.start_turn(1, _Playback())
            processor.submit(_segment(0, "Failure."))

            with self.assertRaisesRegex(RuntimeError, "synthesis failed"):
                await processor.finish_turn(1)

            self.assertFalse(processor.is_active)

        asyncio.run(exercise())


class _ControlledProvider:
    def __init__(self) -> None:
        self.requests: list[SpeechSynthesisRequest] = []
        self.both_started = asyncio.Event()
        self.release_first = asyncio.Event()
        self.release_second = asyncio.Event()

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        self.requests.append(request)
        if len(self.requests) == 2:
            self.both_started.set()
        if request.text.startswith("First"):
            await self.release_first.wait()
        else:
            await self.release_second.wait()
        return SynthesizedAudio(request.text.encode("utf-8"))

    async def available_voices(self) -> tuple[()]:
        return ()


class _BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        self.started.set()
        await self.release.wait()
        return SynthesizedAudio(request.text.encode("utf-8"))

    async def available_voices(self) -> tuple[()]:
        return ()


class _ImmediateProvider:
    async def health(self) -> VoiceProviderHealth:
        return VoiceProviderHealth(VoiceProviderStatus.AVAILABLE)

    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        return SynthesizedAudio(request.text.encode("utf-8"))

    async def available_voices(self) -> tuple[()]:
        return ()


class _FailingProvider(_ImmediateProvider):
    async def synthesize(self, request: SpeechSynthesisRequest) -> SynthesizedAudio:
        del request
        raise RuntimeError("synthesis failed")


class _Playback:
    def __init__(self) -> None:
        self.indices: list[int] = []
        self.texts: list[str] = []

    async def play(
        self,
        segment: ResponseSegment,
        audio: SynthesizedAudio,
    ) -> None:
        self.indices.append(segment.index)
        self.texts.append(audio.data.decode("utf-8"))


def _segment(index: int, text: str, *, turn_id: int = 1) -> ResponseSegment:
    return ResponseSegment(turn_id=turn_id, index=index, text=text)


if __name__ == "__main__":
    unittest.main()
