"""Qt worker for non-blocking direct assistant action requests."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.actions import ActionCancellationToken, ActionRequest
from project_akiha.services.assistant_action_bridge import (
    AssistantActionBridge,
    AssistantActionDispatch,
)


class AssistantActionThread(QThread):
    """Evaluate one typed user action away from the Qt UI thread."""

    result_ready = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        bridge: AssistantActionBridge,
        request: ActionRequest,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._request = request
        self._cancellation_token = ActionCancellationToken()

    def run(self) -> None:
        """Dispatch the request and emit a typed result."""
        if self._is_cancelled():
            self.cancelled.emit()
            return
        try:
            dispatch = asyncio.run(self._dispatch())
        except Exception as error:
            self.failed.emit(str(error))
            return

        if self._is_cancelled():
            self.cancelled.emit()
        else:
            self.result_ready.emit(dispatch)

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self._cancellation_token.cancel()
        self.requestInterruption()

    async def _dispatch(self) -> AssistantActionDispatch:
        return await self._bridge.dispatch(
            self._request,
            cancellation_token=self._cancellation_token,
        )

    def _is_cancelled(self) -> bool:
        return self._cancellation_token.is_cancelled or self.isInterruptionRequested()
