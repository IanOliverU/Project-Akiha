"""Qt handoff for bounded rolling speech-recognition operations."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.voice_session import AudioFrame, EndpointReason
from project_akiha.services.rolling_speech_input import (
    RollingFasterWhisperRecognizer,
)
from project_akiha.services.speech_input import SpeechInputServiceError


class VoiceTranscriptRevisionRelay(QObject):
    """Queue recognizer revisions back onto the owning Qt thread."""

    revision_ready = Signal(object)


class RollingVoiceRecognitionThread(QThread):
    """Process one ordered frame batch without owning microphone hardware."""

    recognition_failed = Signal(str, str)
    recognition_cancelled = Signal()

    def __init__(
        self,
        recognizer: RollingFasterWhisperRecognizer,
        frames: tuple[AudioFrame, ...],
        endpoint_reason: EndpointReason | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._recognizer = recognizer
        self._frames = frames
        self._endpoint_reason = endpoint_reason
        self._is_cancel_requested = False

    @property
    def is_finalizing(self) -> bool:
        return self._endpoint_reason is not None

    def run(self) -> None:
        """Run rolling recognition and expose only privacy-safe failures."""
        if self._is_cancelled():
            self.recognition_cancelled.emit()
            return
        try:
            asyncio.run(self._run_recognition())
        except asyncio.CancelledError:
            self.recognition_cancelled.emit()
        except SpeechInputServiceError as error:
            if self._is_cancelled():
                self.recognition_cancelled.emit()
            else:
                self.recognition_failed.emit(error.code, str(error))
        except Exception as error:
            if self._is_cancelled():
                self.recognition_cancelled.emit()
            else:
                self.recognition_failed.emit(
                    "transcription_failed",
                    f"Speech recognition failed: {error}",
                )

    async def _run_recognition(self) -> None:
        if self._endpoint_reason is None:
            await self._run_latest_partial()
            return

        for frame in self._frames:
            if self._is_cancelled():
                raise asyncio.CancelledError
            self._recognizer.buffer_audio(frame)
        await self._recognizer.finalize(self._endpoint_reason)

    async def _run_latest_partial(self) -> None:
        """Retain a queued batch but infer only its newest cumulative state."""
        if not self._frames:
            return
        for frame in self._frames[:-1]:
            if self._is_cancelled():
                raise asyncio.CancelledError
            self._recognizer.buffer_audio(frame)
        if self._is_cancelled():
            raise asyncio.CancelledError
        await self._recognizer.accept_audio(self._frames[-1])

    def cancel(self) -> None:
        """Invalidate the turn and discard any eventual provider result."""
        self._is_cancel_requested = True
        self.requestInterruption()
        self._recognizer.cancel()

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()
