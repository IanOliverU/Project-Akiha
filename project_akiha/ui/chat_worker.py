"""Qt worker thread for non-blocking chat responses."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.app.chat_controller import ChatController


class ChatResponseThread(QThread):
    """Run one chat request away from the Qt UI thread."""

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
            exchange = asyncio.run(
                self._chat_controller.submit_user_message(self._message)
            )
        except Exception as error:
            self.response_failed.emit(str(error))
            return

        self.response_ready.emit(exchange)
