"""Qt worker for non-blocking AI provider model discovery."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.services.ai_provider_discovery import (
    AIProviderDiscoveryRequest,
    AIProviderDiscoveryResult,
    discover_ai_provider_models,
)

DiscoveryService = Callable[
    [AIProviderDiscoveryRequest],
    AIProviderDiscoveryResult,
]


class AIProviderDiscoveryThread(QThread):
    """Query one AI provider without blocking the Settings window."""

    models_ready = Signal(object)
    discovery_failed = Signal(str)

    def __init__(
        self,
        request: AIProviderDiscoveryRequest,
        parent: QObject | None = None,
        *,
        service: DiscoveryService = discover_ai_provider_models,
    ) -> None:
        super().__init__(parent)
        self._request = request
        self._service = service

    def run(self) -> None:
        """Return models or a privacy-safe diagnostic message."""
        try:
            result = self._service(self._request)
        except Exception as error:
            self.discovery_failed.emit(str(error) or "Provider check failed.")
            return
        self.models_ready.emit(result)
