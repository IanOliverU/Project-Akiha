"""Qt worker thread for non-blocking chat responses."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.app.chat_controller import ChatController
from project_akiha.core.voice_session import (
    ModularResponseContext,
    ModularResponseEvent,
    ModularResponseEventKind,
    VoiceProcessingMode,
)


class ChatResponseThread(QThread):
    """Run one chat request away from the Qt UI thread."""

    response_delta = Signal(str)
    response_ready = Signal(object)
    response_failed = Signal(str)
    response_cancelled = Signal()
    modular_response_event = Signal(object)

    def __init__(
        self,
        chat_controller: ChatController,
        message: str,
        parent: QObject | None = None,
        *,
        response_context: ModularResponseContext | None = None,
    ) -> None:
        super().__init__(parent)
        self._chat_controller = chat_controller
        self._message = message
        self._response_context = response_context or ModularResponseContext(
            response_id=uuid4().hex,
            processing_mode=VoiceProcessingMode.LOCAL_MODULAR,
        )
        self._is_cancel_requested = False
        self._next_event_sequence = 0
        self._has_emitted_started_event = False

    def run(self) -> None:
        """Generate an assistant response in this worker thread."""
        self._ensure_response_started()
        if self._is_cancelled():
            self._emit_response_event(ModularResponseEventKind.CANCELLED)
            self.response_cancelled.emit()
            return

        try:
            response = asyncio.run(self._stream_response())
        except Exception as error:
            self._emit_response_event(
                ModularResponseEventKind.FAILED,
                error_message=_safe_error_message(error),
            )
            self.response_failed.emit(str(error))
            return

        if response is None or self._is_cancelled():
            self._emit_response_event(ModularResponseEventKind.CANCELLED)
            self.response_cancelled.emit()
        else:
            self._emit_response_event(
                ModularResponseEventKind.COMPLETED,
                text=response,
            )
            self.response_ready.emit(response)

    def cancel(self) -> None:
        """Request cancellation of this chat response."""
        self._is_cancel_requested = True
        self.requestInterruption()

    async def _stream_response(self) -> str | None:
        self._ensure_response_started()
        chunks: list[str] = []
        async for chunk in self._chat_controller.stream_user_message(self._message):
            if self._is_cancelled():
                return None

            chunks.append(chunk)
            if chunk:
                self._emit_response_event(ModularResponseEventKind.DELTA, text=chunk)
            self.response_delta.emit(chunk)

            if self._is_cancelled():
                return None

        if self._is_cancelled():
            return None
        return "".join(chunks)

    def _is_cancelled(self) -> bool:
        return self._is_cancel_requested or self.isInterruptionRequested()

    def _ensure_response_started(self) -> None:
        if self._has_emitted_started_event:
            return
        self._has_emitted_started_event = True
        self._emit_response_event(ModularResponseEventKind.STARTED)

    def _emit_response_event(
        self,
        kind: ModularResponseEventKind,
        *,
        text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        sequence_number = self._next_event_sequence
        self._next_event_sequence += 1
        self.modular_response_event.emit(
            ModularResponseEvent(
                context=self._response_context,
                kind=kind,
                sequence_number=sequence_number,
                text=text,
                error_message=error_message,
            )
        )


def _safe_error_message(error: Exception) -> str:
    message = str(error).strip() or type(error).__name__
    return message[:4_096]
