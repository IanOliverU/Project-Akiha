"""Tests for bounded pet diagnostics and reset workers."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.core.pet import PetState, PetStateRecord
from project_akiha.services.pet_diagnostics import PetDiagnosticsSnapshot
from project_akiha.ui.pet_maintenance_worker import (
    PetMaintenanceOperation,
    PetMaintenanceThread,
)


class PetMaintenanceThreadTest(unittest.TestCase):
    """Verify the worker exposes only the two typed maintenance operations."""

    def test_diagnostics_builds_privacy_safe_snapshot(self) -> None:
        service = _Service()
        thread = PetMaintenanceThread(
            service,  # type: ignore[arg-type]
            PetMaintenanceOperation.DIAGNOSTICS,
        )
        received: list[object] = []
        thread.diagnostics_ready.connect(received.append)

        thread.run()

        self.assertEqual(service.calls, ["snapshot"])
        self.assertIsInstance(received[0], PetDiagnosticsSnapshot)

    def test_reset_emits_persisted_record(self) -> None:
        service = _Service()
        thread = PetMaintenanceThread(
            service,  # type: ignore[arg-type]
            PetMaintenanceOperation.RESET,
        )
        received: list[object] = []
        thread.reset_ready.connect(received.append)

        thread.run()

        self.assertEqual(service.calls, ["reset"])
        self.assertEqual(received, [service.record])

    def test_rejects_untyped_operation(self) -> None:
        with self.assertRaises(TypeError):
            PetMaintenanceThread(  # type: ignore[arg-type]
                _Service(),
                "reset",
            )


class _Service:
    def __init__(self) -> None:
        now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
        self.record = PetStateRecord(
            state=PetState.initial(),
            revision=0,
            evaluated_at=now,
            created_at=now,
            updated_at=now,
        )
        self.calls: list[str] = []

    async def snapshot(self) -> PetStateRecord:
        self.calls.append("snapshot")
        return self.record

    async def reset(self) -> PetStateRecord:
        self.calls.append("reset")
        return self.record


if __name__ == "__main__":
    unittest.main()
