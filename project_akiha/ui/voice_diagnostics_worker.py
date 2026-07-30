"""Qt worker for non-blocking voice provider diagnostics."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.services.voice_diagnostics import VoiceDiagnosticsService


class VoiceDiagnosticsThread(QThread):
    """Check configured voice providers away from the UI thread."""

    diagnostics_ready = Signal(object)
    diagnostics_failed = Signal(str)

    def __init__(
        self,
        service: VoiceDiagnosticsService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service

    def run(self) -> None:
        """Run one health check and surface privacy-safe failures."""
        try:
            snapshot = asyncio.run(self._service.check())
        except Exception as error:
            self.diagnostics_failed.emit(f"Voice diagnostics failed: {error}")
            return
        self.diagnostics_ready.emit(snapshot)
