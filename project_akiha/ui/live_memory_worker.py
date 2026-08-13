"""Qt worker for hosted-live memory processing."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.app.chat_controller import CanonicalLiveChatCommit, ChatController


class LiveMemoryProcessingThread(QThread):
    """Process one persisted live exchange without blocking Qt's GUI thread."""

    processing_failed = Signal(str)
    processing_cancelled = Signal()

    def __init__(
        self,
        chat_controller: ChatController,
        commit: CanonicalLiveChatCommit,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chat_controller = chat_controller
        self._commit = commit
        self._is_cancel_requested = False

    def run(self) -> None:
        """Run provider-assisted memory work away from the interface."""
        if self._is_cancelled():
            self.processing_cancelled.emit()
            return
        try:
            asyncio.run(
                self._chat_controller.process_canonical_live_memory(self._commit)
            )
        except Exception as error:
            if self._is_cancelled():
                self.processing_cancelled.emit()
            else:
                self.processing_failed.emit(type(error).__name__)

    def cancel(self) -> None:
        """Discard late worker output during shutdown or conversation reset."""
        self._is_cancel_requested = True
        self.requestInterruption()

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()
