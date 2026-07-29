"""Qt worker thread for non-blocking local speech recognition."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.providers.voice import CapturedAudio
from project_akiha.services.speech_input import (
    SpeechInputService,
    SpeechInputServiceError,
)


class VoiceTranscriptionThread(QThread):
    """Run one local transcription away from the Qt UI thread."""

    transcript_ready = Signal(object)
    transcription_failed = Signal(str, str)
    transcription_cancelled = Signal()

    def __init__(
        self,
        service: SpeechInputService,
        audio: CapturedAudio,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._audio = audio
        self._is_cancel_requested = False

    def run(self) -> None:
        """Transcribe captured audio and discard results after cancellation."""
        if self._is_cancelled():
            self.transcription_cancelled.emit()
            return

        try:
            transcript = asyncio.run(self._service.transcribe(self._audio))
        except SpeechInputServiceError as error:
            if self._is_cancelled():
                self.transcription_cancelled.emit()
            else:
                self.transcription_failed.emit(error.code, str(error))
            return
        except Exception as error:
            if self._is_cancelled():
                self.transcription_cancelled.emit()
            else:
                self.transcription_failed.emit(
                    "transcription_failed",
                    f"Speech recognition failed: {error}",
                )
            return

        if self._is_cancelled():
            self.transcription_cancelled.emit()
        else:
            self.transcript_ready.emit(transcript)

    def cancel(self) -> None:
        """Request cancellation and discard any eventual provider result."""
        self._is_cancel_requested = True
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()
