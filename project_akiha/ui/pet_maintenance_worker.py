"""Qt worker for pet-state diagnostics and explicit reset operations."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.services.pet_diagnostics import build_pet_diagnostics
from project_akiha.services.pet_state import PetStateService


class PetMaintenanceOperation(StrEnum):
    """Closed maintenance operations available to Settings."""

    DIAGNOSTICS = "diagnostics"
    RESET = "reset"


class PetMaintenanceThread(QThread):
    """Run one bounded pet maintenance operation outside the Qt UI thread."""

    diagnostics_ready = Signal(object)
    reset_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: PetStateService,
        operation: PetMaintenanceOperation,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(operation, PetMaintenanceOperation):
            raise TypeError("operation must be a PetMaintenanceOperation value.")
        self._service = service
        self._operation = operation

    def run(self) -> None:
        """Execute the selected typed operation."""
        try:
            if self._operation is PetMaintenanceOperation.DIAGNOSTICS:
                record = asyncio.run(self._service.snapshot())
                self.diagnostics_ready.emit(build_pet_diagnostics(record))
            elif self._operation is PetMaintenanceOperation.RESET:
                self.reset_ready.emit(asyncio.run(self._service.reset()))
        except Exception as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        """Mark the short operation for shutdown coordination."""
        self.requestInterruption()
