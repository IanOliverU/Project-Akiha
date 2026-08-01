"""Behavior checks for the Post-Phase 8 voice-pipeline spike."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator

from project_akiha.providers.ai import OllamaProvider, OpenAICompatibleProvider
from spikes.voice_pipeline.pipeline_spike import (
    AkihaProviderResponder,
    PipelineSpike,
    ResponseSegment,
    SessionLifecycle,
    TranscriptRevision,
    frame_stream,
)


class PipelineSpikeTest(unittest.TestCase):
    def test_partial_intent_never_commits_before_final_transcript(self) -> None:
        async def exercise() -> None:
            intent = _IntentProbe()
            pipeline = PipelineSpike()
            pipeline.start()

            response = await pipeline.run_turn(
                frame_stream((b"one", b"two")),
                _Recognizer(
                    partials=("Open", "Open Spotify"),
                    final="Akiha, please open Spotify.",
                ),
                intent,
                _Responder(("Spotify was started.",)),
                _Synthesizer(),
                _Playback(),
            )

            self.assertEqual(response, "Spotify was started.")
            self.assertEqual(intent.prepared, ["Open", "Open Spotify"])
            self.assertEqual(intent.committed, ["Akiha, please open Spotify."])
            kinds = [event.kind for event in pipeline.events]
            self.assertLess(
                kinds.index("recognition.final"),
                kinds.index("intent.committed"),
            )
            self.assertEqual(pipeline.lifecycle, SessionLifecycle.ACTIVE)

        asyncio.run(exercise())

    def test_first_sentence_plays_before_generation_finishes(self) -> None:
        async def exercise() -> None:
            first_played = asyncio.Event()
            pipeline = PipelineSpike()
            pipeline.start()

            await pipeline.run_turn(
                frame_stream((b"hello",)),
                _Recognizer(partials=("Hello",), final="Hello Akiha."),
                _IntentProbe(),
                _GatedResponder(first_played),
                _Synthesizer(),
                _Playback(first_played=first_played),
            )

            kinds = [event.kind for event in pipeline.events]
            self.assertLess(
                kinds.index("playback.started"),
                kinds.index("generation.completed"),
            )

        asyncio.run(exercise())

    def test_segments_play_in_order_when_synthesis_finishes_out_of_order(self) -> None:
        async def exercise() -> None:
            playback = _Playback()
            pipeline = PipelineSpike()
            pipeline.start()

            await pipeline.run_turn(
                frame_stream((b"hello",)),
                _Recognizer(partials=(), final="Tell me two things."),
                _IntentProbe(),
                _Responder(("First.", " Second.")),
                _Synthesizer(delays={0: 0.02, 1: 0.0}),
                playback,
            )

            self.assertEqual(playback.indices, [0, 1])

        asyncio.run(exercise())

    def test_cancelled_turn_rejects_late_callbacks(self) -> None:
        async def exercise() -> None:
            frame_started = asyncio.Event()
            release_frame = asyncio.Event()
            pipeline = PipelineSpike()
            pipeline.start()
            task = asyncio.create_task(
                pipeline.run_turn(
                    _blocked_frame_stream(frame_started, release_frame),
                    _Recognizer(partials=("Open",), final="Open Spotify."),
                    _IntentProbe(),
                    _Responder(("Started.",)),
                    _Synthesizer(),
                    _Playback(),
                )
            )
            await asyncio.wait_for(frame_started.wait(), timeout=1.0)

            pipeline.cancel_active_turn()
            release_frame.set()

            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(pipeline.accept_callback(1, "recognition.late"))
            self.assertEqual(pipeline.events[-1].kind, "turn.cancelled")

        asyncio.run(exercise())

    def test_response_segmenter_flushes_unpunctuated_tail(self) -> None:
        async def exercise() -> None:
            playback = _Playback()
            pipeline = PipelineSpike()
            pipeline.start()

            await pipeline.run_turn(
                frame_stream((b"hello",)),
                _Recognizer(partials=(), final="Hello."),
                _IntentProbe(),
                _Responder(("A short tail",)),
                _Synthesizer(),
                playback,
            )

            self.assertEqual(playback.texts, ["A short tail"])

        asyncio.run(exercise())

    def test_local_and_hosted_akiha_providers_share_one_pipeline_adapter(self) -> None:
        async def exercise() -> None:
            providers = (
                (
                    "local response.",
                    OllamaProvider(
                        base_url="http://localhost:11434",
                        model="spike",
                        stream_transport=lambda _url, _payload, _timeout: (
                            {"message": {"content": "local response."}},
                            {"done": True},
                        ),
                    ),
                ),
                (
                    "hosted response.",
                    OpenAICompatibleProvider(
                        base_url="https://example.test/v1",
                        model="spike",
                        stream_transport=lambda _url, _payload, _headers, _timeout: (
                            {"choices": [{"delta": {"content": "hosted response."}}]},
                        ),
                    ),
                ),
            )
            for expected, provider in providers:
                playback = _Playback()
                pipeline = PipelineSpike()
                pipeline.start()

                response = await pipeline.run_turn(
                    frame_stream((b"hello",)),
                    _Recognizer(partials=(), final="Hello Akiha."),
                    _IntentProbe(),
                    AkihaProviderResponder(provider),
                    _Synthesizer(),
                    playback,
                )

                self.assertEqual(response, expected)
                self.assertEqual(playback.texts, [expected])

        asyncio.run(exercise())


class _Recognizer:
    def __init__(self, *, partials: tuple[str, ...], final: str) -> None:
        self._partials = iter(enumerate(partials, start=1))
        self._final = final
        self._last_revision = 0

    async def accept(self, frame: bytes) -> TranscriptRevision | None:
        del frame
        try:
            revision, text = next(self._partials)
        except StopIteration:
            return None
        self._last_revision = revision
        return TranscriptRevision(text=text, revision=revision)

    async def finalize(self) -> TranscriptRevision:
        return TranscriptRevision(
            text=self._final,
            revision=self._last_revision + 1,
            is_final=True,
        )


class _IntentProbe:
    def __init__(self) -> None:
        self.prepared: list[str] = []
        self.committed: list[str] = []

    def prepare(self, text: str) -> None:
        self.prepared.append(text)

    def commit(self, text: str) -> None:
        self.committed.append(text)


class _Responder:
    def __init__(self, chunks: tuple[str, ...]) -> None:
        self._chunks = chunks

    async def stream(self, text: str) -> AsyncIterator[str]:
        del text
        for chunk in self._chunks:
            await asyncio.sleep(0)
            yield chunk


class _GatedResponder:
    def __init__(self, first_played: asyncio.Event) -> None:
        self._first_played = first_played

    async def stream(self, text: str) -> AsyncIterator[str]:
        del text
        yield "First sentence."
        await asyncio.wait_for(self._first_played.wait(), timeout=1.0)
        yield " Second sentence."


class _Synthesizer:
    def __init__(self, delays: dict[int, float] | None = None) -> None:
        self._delays = delays or {}

    async def synthesize(self, segment: ResponseSegment) -> bytes:
        await asyncio.sleep(self._delays.get(segment.index, 0.0))
        return segment.text.encode("utf-8")


class _Playback:
    def __init__(self, *, first_played: asyncio.Event | None = None) -> None:
        self._first_played = first_played
        self.indices: list[int] = []
        self.texts: list[str] = []

    async def play(self, segment: ResponseSegment, audio: bytes) -> None:
        self.indices.append(segment.index)
        self.texts.append(audio.decode("utf-8"))
        if self._first_played is not None and segment.index == 0:
            self._first_played.set()
        await asyncio.sleep(0)


async def _blocked_frame_stream(
    frame_started: asyncio.Event,
    release_frame: asyncio.Event,
) -> AsyncIterator[bytes]:
    frame_started.set()
    await release_frame.wait()
    yield b"frame"


if __name__ == "__main__":
    unittest.main()
