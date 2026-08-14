"""Tests for pet-state Qt worker operation selection."""

from __future__ import annotations

import unittest

from project_akiha.core.pet import CareAction
from project_akiha.ui.pet_care_worker import (
    PetCareThread,
    PetRuntimeEvaluationThread,
)


class PetCareThreadTest(unittest.TestCase):
    """Verify the worker never turns arbitrary input into a care action."""

    def test_snapshot_operation_emits_snapshot(self) -> None:
        service = _FakePetStateService()
        emitted: list[object] = []
        thread = PetCareThread(service)  # type: ignore[arg-type]
        thread.snapshot_ready.connect(emitted.append)

        thread.run()

        self.assertEqual(emitted, [service.snapshot_value])
        self.assertEqual(service.actions, [])

    def test_care_operation_forwards_typed_action(self) -> None:
        service = _FakePetStateService()
        emitted: list[object] = []
        thread = PetCareThread(  # type: ignore[arg-type]
            service,
            CareAction.SPEND_TIME,
        )
        thread.care_ready.connect(emitted.append)

        thread.run()

        self.assertEqual(service.actions, [CareAction.SPEND_TIME])
        self.assertEqual(emitted, [service.care_value])

    def test_constructor_rejects_untyped_action(self) -> None:
        with self.assertRaises(TypeError):
            PetCareThread(  # type: ignore[arg-type]
                _FakePetStateService(),
                "feed",
            )

    def test_runtime_worker_emits_elapsed_evaluation(self) -> None:
        service = _FakePetStateService()
        emitted: list[object] = []
        thread = PetRuntimeEvaluationThread(service)  # type: ignore[arg-type]
        thread.evaluated.connect(emitted.append)

        thread.run()

        self.assertEqual(emitted, [service.runtime_value])
        self.assertEqual(service.runtime_evaluations, 1)


class _FakePetStateService:
    def __init__(self) -> None:
        self.snapshot_value = object()
        self.care_value = object()
        self.runtime_value = object()
        self.actions: list[CareAction] = []
        self.runtime_evaluations = 0

    async def snapshot(self) -> object:
        return self.snapshot_value

    async def apply_care_action(self, action: CareAction) -> object:
        self.actions.append(action)
        return self.care_value

    async def evaluate_runtime(self) -> object:
        self.runtime_evaluations += 1
        return self.runtime_value


if __name__ == "__main__":
    unittest.main()
