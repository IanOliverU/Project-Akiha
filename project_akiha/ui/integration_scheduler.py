"""Queued Qt handoff for callbacks from optional integration workers."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal


class QtAppThreadScheduler(QObject):
    """Execute worker callbacks on the owning Qt application thread."""

    _scheduled = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._scheduled.connect(
            self._run,
            Qt.ConnectionType.QueuedConnection,
        )

    def schedule(self, callback: Callable[[], None]) -> None:
        """Queue a callable without executing it in the provider thread."""
        self._scheduled.emit(callback)

    def _run(self, callback: object) -> None:
        if callable(callback):
            callback()
