"""Qt worker for non-blocking assistant subtitle translation."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.services.assistant_translation import AssistantTranslationService


class AssistantTranslationThread(QThread):
    """Translate one completed assistant response away from the UI thread."""

    translation_ready = Signal(str)
    translation_failed = Signal(str)
    translation_cancelled = Signal()

    def __init__(
        self,
        service: AssistantTranslationService,
        text: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._text = text
        self._is_cancel_requested = False

    def run(self) -> None:
        """Translate the response and publish only validated subtitle text."""
        if self._is_cancelled():
            self.translation_cancelled.emit()
            return
        try:
            translation = asyncio.run(self._service.translate_to_english(self._text))
        except Exception as error:
            if self._is_cancelled():
                self.translation_cancelled.emit()
            else:
                self.translation_failed.emit(type(error).__name__)
            return

        if self._is_cancelled():
            self.translation_cancelled.emit()
        else:
            self.translation_ready.emit(translation)

    def cancel(self) -> None:
        """Request that late translation output be discarded."""
        self._is_cancel_requested = True
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()
