"""Qt worker thread for non-blocking chat responses."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.app.chat_controller import ChatController


class ChatResponseThread(QThread):
    """Run one chat request away from the Qt UI thread."""

    response_delta = Signal(str)
    response_ready = Signal(object)
    response_failed = Signal(str)
    response_cancelled = Signal()

    def __init__(
        self,
        chat_controller: ChatController,
        message: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chat_controller = chat_controller
        self._message = message
        self._is_cancel_requested = False

    def run(self) -> None:
        """Generate an assistant response in this worker thread."""
        if self._is_cancelled():
            self.response_cancelled.emit()
            return

        try:
            response = asyncio.run(self._stream_response())
        except Exception as error:
            self.response_failed.emit(str(error))
            return

        if response is None or self._is_cancelled():
            self.response_cancelled.emit()
        else:
            self.response_ready.emit(response)

    def cancel(self) -> None:
        """Request cancellation of this chat response."""
        self._is_cancel_requested = True
        self.requestInterruption()

    async def _stream_response(self) -> str | None:
        chunks: list[str] = []
        async for chunk in self._chat_controller.stream_user_message(self._message):
            if self._is_cancelled():
                return None

            chunks.append(chunk)
            self.response_delta.emit(chunk)

            if self._is_cancelled():
                return None

        if self._is_cancelled():
            return None
        return "".join(chunks)

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()
