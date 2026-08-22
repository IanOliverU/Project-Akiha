"""Qt worker for pet-state diagnostics and explicit reset operations."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.services.pet_diagnostics import build_pet_diagnostics
from project_akiha.services.pet_state import PetStateService
from project_akiha.services.pet_status import PetRuntimeStatus, PetStatusService


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
        *,
        status_service: PetStatusService | None = None,
        runtime_status: PetRuntimeStatus | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not isinstance(operation, PetMaintenanceOperation):
            raise TypeError("operation must be a PetMaintenanceOperation value.")
        self._service = service
        self._operation = operation
        self._status_service = status_service
        self._runtime_status = runtime_status
        if (status_service is None) != (runtime_status is None):
            raise ValueError(
                "status_service and runtime_status must be provided together."
            )

    def run(self) -> None:
        """Execute the selected typed operation."""
        try:
            if self._operation is PetMaintenanceOperation.DIAGNOSTICS:
                if self._status_service is not None:
                    assert self._runtime_status is not None
                    self.diagnostics_ready.emit(
                        asyncio.run(self._status_service.snapshot(self._runtime_status))
                    )
                else:
                    record = asyncio.run(self._service.snapshot())
                    self.diagnostics_ready.emit(build_pet_diagnostics(record))
            elif self._operation is PetMaintenanceOperation.RESET:
                self.reset_ready.emit(asyncio.run(self._service.reset()))
        except Exception as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        """Mark the short operation for shutdown coordination."""
        self.requestInterruption()
