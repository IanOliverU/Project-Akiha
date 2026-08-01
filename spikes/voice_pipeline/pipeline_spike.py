"""Framework-neutral concurrent voice-pipeline spike.

This module is deliberately outside ``project_akiha``. It validates pipeline
semantics without becoming part of the packaged application.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable, AsyncIterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from project_akiha.providers.ai import AIProvider, ChatMessage


class SessionLifecycle(StrEnum):
    """Top-level ownership state for the spike session."""

    IDLE = "idle"
    ACTIVE = "active"
    STOPPING = "stopping"


@dataclass(frozen=True, slots=True)
class TranscriptRevision:
    """One replaceable partial or authoritative final transcript revision."""

    text: str
    revision: int
    is_final: bool = False
    detected_language: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("Transcript revision must be positive.")
        if not self.text.strip():
            raise ValueError("Transcript revision text cannot be empty.")
        if self.confidence is not None and (
            isinstance(self.confidence, bool) or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("Transcript confidence must be between zero and one.")


@dataclass(frozen=True, slots=True)
class ResponseSegment:
    """A stable response span that may be synthesized independently."""

    turn_id: int
    index: int
    text: str
    is_final: bool = False

    def __post_init__(self) -> None:
        if self.turn_id < 1:
            raise ValueError("Turn ID must be positive.")
        if self.index < 0:
            raise ValueError("Response segment index cannot be negative.")
        if not self.text.strip():
            raise ValueError("Response segment text cannot be empty.")


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    """Privacy-safe evidence emitted by the spike."""

    turn_id: int
    kind: str
    index: int | None = None


class StreamingRecognizer(Protocol):
    """Accept frames during speech and emit one authoritative final."""

    async def accept(self, frame: object) -> TranscriptRevision | None:
        """Consume one bounded frame and optionally return a partial revision."""

    async def finalize(self) -> TranscriptRevision:
        """Return the accepted final transcript."""


class IntentProbe(Protocol):
    """Observe speculative text separately from committed final text."""

    def prepare(self, text: str) -> None:
        """Prepare replaceable intent state without side effects."""

    def commit(self, text: str) -> None:
        """Commit intent from one accepted final transcript."""


class StreamingResponder(Protocol):
    """Stream response text from either a local LLM or hosted text API."""

    def stream(self, text: str) -> AsyncIterator[str]:
        """Yield canonical assistant response deltas."""


class AkihaProviderResponder:
    """Adapt any existing local or hosted Akiha provider to the spike."""

    def __init__(self, provider: AIProvider) -> None:
        self._provider = provider

    def stream(self, text: str) -> AsyncIterator[str]:
        message = ChatMessage(role="user", content=text.strip())
        return self._provider.stream_response((message,))


class SegmentSynthesizer(Protocol):
    """Synthesize one stable response segment."""

    async def synthesize(self, segment: ResponseSegment) -> bytes:
        """Return temporary audio bytes for one segment."""


class OrderedPlayback(Protocol):
    """Play synthesized segments in canonical order."""

    async def play(self, segment: ResponseSegment, audio: bytes) -> None:
        """Play one synthesized segment."""


class StableResponseSegmenter:
    """Extract complete sentence spans from streamed response deltas."""

    _BOUNDARIES = frozenset(".!?。！？")

    def __init__(self, turn_id: int) -> None:
        self._turn_id = turn_id
        self._buffer = ""
        self._next_index = 0

    def feed(self, delta: str) -> tuple[ResponseSegment, ...]:
        """Append a delta and return newly stable sentence segments."""
        self._buffer += delta
        segments: list[ResponseSegment] = []
        while True:
            boundary = next(
                (
                    index
                    for index, character in enumerate(self._buffer)
                    if character in self._BOUNDARIES
                ),
                None,
            )
            if boundary is None:
                break
            text = self._buffer[: boundary + 1].strip()
            self._buffer = self._buffer[boundary + 1 :].lstrip()
            if text:
                segments.append(self._make_segment(text, is_final=False))
        return tuple(segments)

    def finish(self) -> ResponseSegment | None:
        """Return a final stable tail when generation completes."""
        text = self._buffer.strip()
        self._buffer = ""
        if not text:
            return None
        return self._make_segment(text, is_final=True)

    def _make_segment(self, text: str, *, is_final: bool) -> ResponseSegment:
        segment = ResponseSegment(
            turn_id=self._turn_id,
            index=self._next_index,
            text=text,
            is_final=is_final,
        )
        self._next_index += 1
        return segment


class PipelineSpike:
    """Prove safe recognition and overlapping response stages with fakes."""

    def __init__(self) -> None:
        self._lifecycle = SessionLifecycle.IDLE
        self._next_turn_id = 1
        self._active_turn_id: int | None = None
        self._cancelled_turns: set[int] = set()
        self._events: list[PipelineEvent] = []

    @property
    def lifecycle(self) -> SessionLifecycle:
        return self._lifecycle

    @property
    def events(self) -> tuple[PipelineEvent, ...]:
        return tuple(self._events)

    def start(self) -> None:
        """Start one explicit spike session."""
        if self._lifecycle != SessionLifecycle.IDLE:
            raise RuntimeError("Pipeline session is already active.")
        self._lifecycle = SessionLifecycle.ACTIVE

    def stop(self) -> None:
        """Cancel the active turn and stop the session."""
        if self._lifecycle == SessionLifecycle.IDLE:
            return
        self._lifecycle = SessionLifecycle.STOPPING
        self.cancel_active_turn()
        self._lifecycle = SessionLifecycle.IDLE

    def cancel_active_turn(self) -> None:
        """Reject every later callback for the current turn."""
        if self._active_turn_id is not None:
            self._cancelled_turns.add(self._active_turn_id)
            self._record(self._active_turn_id, "turn.cancelled", allow_cancelled=True)
            self._active_turn_id = None

    def accept_callback(self, turn_id: int, kind: str) -> bool:
        """Accept only callbacks belonging to the live, uncancelled turn."""
        if (
            turn_id != self._active_turn_id
            or turn_id in self._cancelled_turns
            or self._lifecycle != SessionLifecycle.ACTIVE
        ):
            return False
        self._record(turn_id, kind)
        return True

    async def run_turn(
        self,
        frames: AsyncIterable[object],
        recognizer: StreamingRecognizer,
        intent: IntentProbe,
        responder: StreamingResponder,
        synthesizer: SegmentSynthesizer,
        playback: OrderedPlayback,
    ) -> str:
        """Run one fake turn through concurrent recognition and speech stages."""
        if self._lifecycle != SessionLifecycle.ACTIVE:
            raise RuntimeError("Pipeline session is not active.")
        if self._active_turn_id is not None:
            raise RuntimeError("Another turn is already active.")

        turn_id = self._next_turn_id
        self._next_turn_id += 1
        self._active_turn_id = turn_id
        self._record(turn_id, "capture.started")

        async for frame in frames:
            self._raise_if_cancelled(turn_id)
            revision = await recognizer.accept(frame)
            if revision is None:
                continue
            if revision.is_final:
                raise ValueError("Recognizer emitted a final before finalization.")
            intent.prepare(revision.text)
            self._record(turn_id, "intent.speculative", revision.revision)

        self._record(turn_id, "capture.completed")
        final_revision = await recognizer.finalize()
        self._raise_if_cancelled(turn_id)
        if not final_revision.is_final:
            raise ValueError("Recognizer finalization did not return a final revision.")

        self._record(turn_id, "recognition.final", final_revision.revision)
        intent.commit(final_revision.text)
        self._record(turn_id, "intent.committed")

        response_chunks: list[str] = []
        segmenter = StableResponseSegmenter(turn_id)
        playback_queue: asyncio.Queue[
            tuple[ResponseSegment, asyncio.Task[bytes]] | None
        ] = asyncio.Queue()
        playback_worker = asyncio.create_task(
            self._playback_worker(turn_id, playback_queue, playback)
        )

        try:
            async for chunk in responder.stream(final_revision.text):
                self._raise_if_cancelled(turn_id)
                response_chunks.append(chunk)
                self._record(turn_id, "generation.delta")
                for segment in segmenter.feed(chunk):
                    await self._queue_segment(
                        turn_id,
                        segment,
                        synthesizer,
                        playback_queue,
                    )

            tail = segmenter.finish()
            if tail is not None:
                await self._queue_segment(
                    turn_id,
                    tail,
                    synthesizer,
                    playback_queue,
                )
            self._record(turn_id, "generation.completed")
            await playback_queue.put(None)
            await playback_worker
        except BaseException:
            playback_worker.cancel()
            await asyncio.gather(playback_worker, return_exceptions=True)
            raise
        finally:
            if self._active_turn_id == turn_id:
                self._active_turn_id = None

        self._record(turn_id, "turn.completed")
        return "".join(response_chunks)

    async def _queue_segment(
        self,
        turn_id: int,
        segment: ResponseSegment,
        synthesizer: SegmentSynthesizer,
        queue: asyncio.Queue[tuple[ResponseSegment, asyncio.Task[bytes]] | None],
    ) -> None:
        self._raise_if_cancelled(turn_id)
        self._record(turn_id, "synthesis.queued", segment.index)
        task = asyncio.create_task(synthesizer.synthesize(segment))
        await queue.put((segment, task))

    async def _playback_worker(
        self,
        turn_id: int,
        queue: asyncio.Queue[tuple[ResponseSegment, asyncio.Task[bytes]] | None],
        playback: OrderedPlayback,
    ) -> None:
        while True:
            queued = await queue.get()
            if queued is None:
                return
            segment, synthesis = queued
            audio = await synthesis
            self._raise_if_cancelled(turn_id)
            self._record(turn_id, "synthesis.completed", segment.index)
            self._record(turn_id, "playback.started", segment.index)
            await playback.play(segment, audio)
            self._record(turn_id, "playback.completed", segment.index)

    def _raise_if_cancelled(self, turn_id: int) -> None:
        if turn_id in self._cancelled_turns or turn_id != self._active_turn_id:
            raise asyncio.CancelledError

    def _record(
        self,
        turn_id: int,
        kind: str,
        index: int | None = None,
        *,
        allow_cancelled: bool = False,
    ) -> None:
        if not allow_cancelled and turn_id in self._cancelled_turns:
            return
        self._events.append(PipelineEvent(turn_id=turn_id, kind=kind, index=index))


async def frame_stream(frames: Sequence[bytes]) -> AsyncIterator[bytes]:
    """Yield bounded fake frames while giving concurrent tasks time to run."""
    for frame in frames:
        await asyncio.sleep(0)
        yield frame
