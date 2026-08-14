"""Qt worker for non-blocking pet-state reads and care actions."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal

from project_akiha.core.pet import CareAction
from project_akiha.services.pet_state import PetStateService


class PetCareThread(QThread):
    """Run one pet-state operation away from the Qt UI thread."""

    snapshot_ready = Signal(object)
    care_ready = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: PetStateService,
        action: CareAction | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if action is not None and not isinstance(action, CareAction):
            raise TypeError("action must be a CareAction value or None.")
        self._service = service
        self._action = action

    def run(self) -> None:
        """Read the current snapshot or apply one typed care action."""
        try:
            if self._action is None:
                self.snapshot_ready.emit(asyncio.run(self._service.snapshot()))
            else:
                self.care_ready.emit(
                    asyncio.run(self._service.apply_care_action(self._action))
                )
        except Exception as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        """Mark the short operation for shutdown coordination."""
        self.requestInterruption()


class PetRuntimeEvaluationThread(QThread):
    """Settle elapsed pet-state decay away from the Qt UI thread."""

    evaluated = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: PetStateService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service

    def run(self) -> None:
        """Apply one elapsed runtime evaluation."""
        try:
            self.evaluated.emit(asyncio.run(self._service.evaluate_runtime()))
        except Exception as error:
            self.failed.emit(str(error))

    def cancel(self) -> None:
        """Mark the short operation for shutdown coordination."""
        self.requestInterruption()
