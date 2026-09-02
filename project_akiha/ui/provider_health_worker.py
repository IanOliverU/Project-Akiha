"""Non-blocking GPT-SoVITS monitoring for the Qt application."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from project_akiha.config import VoiceConfig
from project_akiha.services.gpt_sovits_engine_manager import (
    GptSoVitsEngineManager,
    GptSoVitsEngineStatus,
)


class GptSoVitsHealthThread(QThread):
    """Run endpoint probing and bounded recovery away from the UI thread."""

    completed = Signal(object)

    def __init__(
        self,
        manager: GptSoVitsEngineManager,
        config: VoiceConfig,
    ) -> None:
        super().__init__()
        self._manager = manager
        self._config = config

    def run(self) -> None:
        try:
            status = self._manager.monitor_and_recover(self._config)
        except Exception:
            status = GptSoVitsEngineStatus(
                "unavailable",
                "GPT-SoVITS health monitoring failed safely.",
                True,
            )
        self.completed.emit(status)
