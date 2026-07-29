"""Qt worker thread for non-blocking speech synthesis."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.services.speech_output import (
    SpeechOutputService,
    SpeechOutputServiceError,
)


class VoiceSynthesisThread(QThread):
    """Run one speech synthesis request away from the Qt UI thread."""

    audio_ready = Signal(object)
    synthesis_failed = Signal(str, str)
    synthesis_cancelled = Signal()

    def __init__(
        self,
        service: SpeechOutputService,
        text: str,
        voice_id: str | None,
        language: str,
        speaking_rate: float,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._text = text
        self._voice_id = voice_id
        self._language = language
        self._speaking_rate = speaking_rate
        self._is_cancel_requested = False

    def run(self) -> None:
        """Synthesize speech and discard encoded audio after cancellation."""
        if self._is_cancelled():
            self.synthesis_cancelled.emit()
            return

        try:
            audio = asyncio.run(
                self._service.synthesize(
                    self._text,
                    voice_id=self._voice_id,
                    language=self._language,
                    speaking_rate=self._speaking_rate,
                )
            )
        except SpeechOutputServiceError as error:
            if self._is_cancelled():
                self.synthesis_cancelled.emit()
            else:
                self.synthesis_failed.emit(error.code, str(error))
            return
        except Exception as error:
            if self._is_cancelled():
                self.synthesis_cancelled.emit()
            else:
                self.synthesis_failed.emit(
                    "synthesis_failed",
                    f"Speech synthesis failed: {error}",
                )
            return

        if self._is_cancelled():
            self.synthesis_cancelled.emit()
        else:
            self.audio_ready.emit(audio)

    def cancel(self) -> None:
        """Request cancellation and discard any eventual provider result."""
        self._is_cancel_requested = True
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()
