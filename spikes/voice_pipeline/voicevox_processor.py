"""Ordered concurrent VOICEVOX processor prototype for stable segments."""

from __future__ import annotations

import asyncio
from typing import Protocol

from project_akiha.providers.voice import SynthesizedAudio
from project_akiha.services.speech_output import SpeechOutputService
from spikes.voice_pipeline.pipeline_spike import ResponseSegment


class SegmentAudioPlayback(Protocol):
    """Play one synthesized response segment without retaining its audio."""

    async def play(
        self,
        segment: ResponseSegment,
        audio: SynthesizedAudio,
    ) -> None:
        """Play one segment and return after playback completes."""


class OrderedVoiceVoxProcessor:
    """Overlap bounded synthesis while preserving canonical playback order."""

    def __init__(
        self,
        service: SpeechOutputService,
        *,
        voice_id: str | None = None,
        language: str = "ja-JP",
        speaking_rate: float = 1.0,
        maximum_concurrent_synthesis: int = 2,
    ) -> None:
        if not language.strip():
            raise ValueError("VOICEVOX processor language cannot be empty.")
        if not 0.5 <= speaking_rate <= 2.0:
            raise ValueError("VOICEVOX processor rate must be between 0.5 and 2.0.")
        if maximum_concurrent_synthesis < 1:
            raise ValueError("VOICEVOX synthesis concurrency must be positive.")
        self._service = service
        self._voice_id = voice_id
        self._language = language.strip()
        self._speaking_rate = speaking_rate
        self._semaphore = asyncio.Semaphore(maximum_concurrent_synthesis)
        self._active_turn_id: int | None = None
        self._next_segment_index = 0
        self._queue: (
            asyncio.Queue[tuple[ResponseSegment, asyncio.Task[SynthesizedAudio]] | None]
            | None
        ) = None
        self._playback_worker: asyncio.Task[None] | None = None
        self._synthesis_tasks: set[asyncio.Task[SynthesizedAudio]] = set()
        self._cancelled_turns: set[int] = set()

    @property
    def is_active(self) -> bool:
        return self._active_turn_id is not None

    def start_turn(self, turn_id: int, playback: SegmentAudioPlayback) -> None:
        """Start one ordered synthesis and playback turn."""
        if turn_id < 1:
            raise ValueError("VOICEVOX processor turn ID must be positive.")
        if self.is_active:
            raise RuntimeError("VOICEVOX processor already owns a turn.")
        self._active_turn_id = turn_id
        self._next_segment_index = 0
        self._queue = asyncio.Queue()
        self._playback_worker = asyncio.create_task(
            self._run_playback(turn_id, self._queue, playback)
        )

    def submit(self, segment: ResponseSegment) -> None:
        """Schedule one stable segment for bounded synthesis."""
        if self._active_turn_id is None or self._queue is None:
            raise RuntimeError("VOICEVOX processor has no active turn.")
        if self._playback_worker is None or self._playback_worker.done():
            raise RuntimeError("VOICEVOX playback worker is unavailable.")
        if segment.turn_id != self._active_turn_id:
            raise ValueError("VOICEVOX segment belongs to a different turn.")
        if segment.index != self._next_segment_index:
            raise ValueError("VOICEVOX segments must be submitted in order.")

        synthesis = asyncio.create_task(self._synthesize(segment))
        self._synthesis_tasks.add(synthesis)
        synthesis.add_done_callback(self._synthesis_tasks.discard)
        self._queue.put_nowait((segment, synthesis))
        self._next_segment_index += 1

    async def finish_turn(self, turn_id: int) -> None:
        """Finish queued segments and release all temporary turn state."""
        self._require_active_turn(turn_id)
        assert self._queue is not None
        assert self._playback_worker is not None
        self._queue.put_nowait(None)
        try:
            await self._playback_worker
        except BaseException:
            await self._cancel_tasks()
            raise
        finally:
            self._clear_turn(turn_id)

    async def cancel_turn(self, turn_id: int) -> bool:
        """Cancel synthesis and playback for one active turn."""
        if self._active_turn_id != turn_id:
            return False
        self._cancelled_turns.add(turn_id)
        await self._cancel_tasks()
        self._clear_turn(turn_id)
        return True

    async def _synthesize(self, segment: ResponseSegment) -> SynthesizedAudio:
        async with self._semaphore:
            if segment.turn_id in self._cancelled_turns:
                raise asyncio.CancelledError
            audio = await self._service.synthesize(
                segment.text,
                voice_id=self._voice_id,
                language=self._language,
                speaking_rate=self._speaking_rate,
            )
            if segment.turn_id in self._cancelled_turns:
                raise asyncio.CancelledError
            return audio

    async def _run_playback(
        self,
        turn_id: int,
        queue: asyncio.Queue[
            tuple[ResponseSegment, asyncio.Task[SynthesizedAudio]] | None
        ],
        playback: SegmentAudioPlayback,
    ) -> None:
        while True:
            queued = await queue.get()
            if queued is None:
                return
            segment, synthesis = queued
            audio = await synthesis
            if turn_id in self._cancelled_turns:
                raise asyncio.CancelledError
            await playback.play(segment, audio)

    async def _cancel_tasks(self) -> None:
        tasks: list[asyncio.Task[object]] = []
        if self._playback_worker is not None and not self._playback_worker.done():
            self._playback_worker.cancel()
            tasks.append(self._playback_worker)
        for synthesis in tuple(self._synthesis_tasks):
            if not synthesis.done():
                synthesis.cancel()
                tasks.append(synthesis)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _require_active_turn(self, turn_id: int) -> None:
        if self._active_turn_id != turn_id:
            raise RuntimeError("VOICEVOX processor does not own that turn.")

    def _clear_turn(self, turn_id: int) -> None:
        if self._active_turn_id != turn_id:
            return
        self._active_turn_id = None
        self._next_segment_index = 0
        self._queue = None
        self._playback_worker = None
        self._synthesis_tasks.clear()
        self._cancelled_turns.discard(turn_id)
