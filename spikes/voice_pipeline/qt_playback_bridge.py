"""Thread-safe segment adapter for Akiha's existing Qt playback owner."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Event

from PySide6.QtCore import QObject, Qt, Signal

from project_akiha.providers.voice import (
    AudioPlayback,
    AudioPlaybackError,
    SynthesizedAudio,
)
from spikes.voice_pipeline.pipeline_spike import ResponseSegment


@dataclass(slots=True)
class _PlaybackRequest:
    segment: ResponseSegment
    audio: SynthesizedAudio
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future[None]
    cancelled: Event = field(default_factory=Event)


class QtSegmentPlaybackBridge(QObject):
    """Queue one ordered segment at a time onto the Qt playback owner thread."""

    _play_requested = Signal(object)
    _cancel_requested = Signal(object)

    def __init__(
        self,
        playback: AudioPlayback,
        parent: QObject | None = None,
    ) -> None:
        if parent is None and isinstance(playback, QObject):
            parent = playback
        super().__init__(parent)
        if isinstance(playback, QObject) and playback.thread() != self.thread():
            raise ValueError("Qt playback bridge must share its owner's Qt thread.")
        self._playback = playback
        self._active_request: _PlaybackRequest | None = None
        self._play_requested.connect(
            self._start_playback,
            Qt.ConnectionType.QueuedConnection,
        )
        self._cancel_requested.connect(
            self._cancel_playback,
            Qt.ConnectionType.QueuedConnection,
        )

    async def play(
        self,
        segment: ResponseSegment,
        audio: SynthesizedAudio,
    ) -> None:
        """Play on the Qt owner thread and await its terminal callback."""
        if not isinstance(segment, ResponseSegment):
            raise TypeError("Qt playback bridge requires a response segment.")
        if not isinstance(audio, SynthesizedAudio):
            raise TypeError("Qt playback bridge requires synthesized audio.")
        loop = asyncio.get_running_loop()
        request = _PlaybackRequest(
            segment=segment,
            audio=audio,
            loop=loop,
            future=loop.create_future(),
        )
        self._play_requested.emit(request)
        try:
            await request.future
        except asyncio.CancelledError:
            request.cancelled.set()
            self._cancel_requested.emit(request)
            raise

    def _start_playback(self, request: object) -> None:
        if not isinstance(request, _PlaybackRequest) or request.cancelled.is_set():
            return
        if self._active_request is not None:
            self._reject(
                request,
                AudioPlaybackError(
                    "playback_busy",
                    "Qt segment playback already owns an active segment.",
                ),
            )
            return
        self._active_request = request
        try:
            self._playback.play(
                request.audio,
                on_started=lambda: None,
                on_finished=lambda current=request: self._finish(current),
                on_error=lambda code, message, current=request: self._fail(
                    current,
                    code,
                    message,
                ),
            )
        except AudioPlaybackError as error:
            self._active_request = None
            self._reject(request, error)
        except Exception as error:
            self._active_request = None
            self._reject(
                request,
                AudioPlaybackError(
                    "playback_failed",
                    f"Qt segment playback failed: {error}",
                ),
            )

    def _cancel_playback(self, request: object) -> None:
        if not isinstance(request, _PlaybackRequest):
            return
        if self._active_request is not request:
            return
        self._active_request = None
        self._playback.stop()

    def _finish(self, request: _PlaybackRequest) -> None:
        if self._active_request is not request:
            return
        self._active_request = None
        request.loop.call_soon_threadsafe(_resolve, request.future)

    def _fail(
        self,
        request: _PlaybackRequest,
        code: str,
        message: str,
    ) -> None:
        if self._active_request is not request:
            return
        self._active_request = None
        self._reject(request, AudioPlaybackError(code, message))

    @staticmethod
    def _reject(request: _PlaybackRequest, error: AudioPlaybackError) -> None:
        request.loop.call_soon_threadsafe(_reject, request.future, error)


def _resolve(future: asyncio.Future[None]) -> None:
    if not future.done():
        future.set_result(None)


def _reject(
    future: asyncio.Future[None],
    error: AudioPlaybackError,
) -> None:
    if not future.done():
        future.set_exception(error)
