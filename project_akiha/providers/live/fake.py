"""In-memory Gemini transport for deterministic live-session verification."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from project_akiha.core.voice_session import LiveSessionError
from project_akiha.providers.live.gemini import (
    GeminiLiveTransportConfig,
    GeminiTransportEvent,
)

_CLOSE = object()


class FakeGeminiLiveTransport:
    """Record transport calls and emit explicitly queued provider events."""

    def __init__(self, *, connect_error: LiveSessionError | None = None) -> None:
        self.connect_error = connect_error
        self.connected_config: GeminiLiveTransportConfig | None = None
        self.sent_audio: list[tuple[bytes, str]] = []
        self.audio_stream_end_count = 0
        self.interrupt_count = 0
        self.close_count = 0
        self._events: asyncio.Queue[GeminiTransportEvent | object] = asyncio.Queue()

    async def connect(self, config: GeminiLiveTransportConfig) -> None:
        """Record setup or raise the configured connection failure."""
        if self.connect_error is not None:
            raise self.connect_error
        self.connected_config = config

    async def send_audio(self, data: bytes, mime_type: str) -> None:
        """Record one copied PCM frame."""
        self.sent_audio.append((bytes(data), mime_type))

    async def end_audio_stream(self) -> None:
        """Record an end-of-user-audio signal."""
        self.audio_stream_end_count += 1

    async def interrupt(self) -> None:
        """Record one response-interruption request."""
        self.interrupt_count += 1

    async def close(self) -> None:
        """Release the fake receive stream idempotently."""
        self.close_count += 1
        await self._events.put(_CLOSE)

    async def emit(self, event: GeminiTransportEvent) -> None:
        """Queue one provider event for the receive loop."""
        await self._events.put(event)

    async def finish(self) -> None:
        """End the receive stream without incrementing transport close calls."""
        await self._events.put(_CLOSE)

    async def receive(self) -> AsyncIterator[GeminiTransportEvent]:
        """Yield queued events until the close sentinel arrives."""
        while True:
            event = await self._events.get()
            if event is _CLOSE:
                return
            assert isinstance(event, GeminiTransportEvent)
            yield event
