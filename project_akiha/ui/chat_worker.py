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

    def __init__(
        self,
        chat_controller: ChatController,
        message: str,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chat_controller = chat_controller
        self._message = message

    def run(self) -> None:
        """Generate an assistant response in this worker thread."""
        try:
            asyncio.run(self._stream_response())
        except Exception as error:
            self.response_failed.emit(str(error))
            return

        self.response_ready.emit(None)

    async def _stream_response(self) -> None:
        async for chunk in self._chat_controller.stream_user_message(self._message):
            self.response_delta.emit(chunk)
