"""Tests for injected-clock pet-state service orchestration."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.pet import DecayStatus, PetState, PetWellbeing
from project_akiha.database import SQLitePetStateRepository
from project_akiha.services.pet_state import PetStateService


class PetStateServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify catch-up, runtime evaluation, and the typed mutation surface."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self._database_path = Path(self._temporary_directory.name) / "akiha.sqlite3"
        self._repository = SQLitePetStateRepository(self._database_path)
        self._clock = _FakeClock(datetime(2026, 8, 14, 8, 0, tzinfo=UTC))

    async def test_initialize_creates_typed_defaults_once(self) -> None:
        service = PetStateService(self._repository, self._clock)

        first = await service.initialize()
        second = await service.initialize()
        history = await self._repository.get_recent_history(10)

        self.assertEqual(first.record, second.record)
        self.assertEqual(first.record.state, PetState.initial())
        self.assertEqual(first.record.revision, 0)
        self.assertEqual(first.decay_outcome.status, DecayStatus.NO_ELAPSED_TIME)
        self.assertEqual(len(history), 1)

    async def test_initialize_caps_offline_catch_up_at_twelve_hours(self) -> None:
        await self._repository.load_or_create(
            PetState.initial(),
            self._clock.now() - timedelta(days=1),
        )
        service = PetStateService(self._repository, self._clock)

        evaluation = await service.initialize()

        wellbeing = evaluation.record.state.wellbeing
        self.assertEqual(wellbeing.satiety, 64)
        self.assertEqual(wellbeing.energy, 68)
        self.assertEqual(wellbeing.attention, 62)
        self.assertEqual(evaluation.record.revision, 1)
        self.assertTrue(evaluation.decay_outcome.was_capped)
        self.assertEqual(
            evaluation.decay_outcome.applied_elapsed_seconds,
            12 * 60 * 60,
        )

    async def test_runtime_evaluation_accumulates_partial_intervals(self) -> None:
        service = PetStateService(self._repository, self._clock)
        await service.initialize()

        self._clock.advance(timedelta(minutes=20))
        partial = await service.evaluate_runtime()
        self._clock.advance(timedelta(minutes=25))
        completed = await service.evaluate_runtime()
        history = await self._repository.get_recent_history(10)

        self.assertEqual(partial.record.state.wellbeing.satiety, 80)
        self.assertEqual(
            partial.record.state.decay_progress.satiety_seconds,
            20 * 60,
        )
        self.assertEqual(completed.record.state.wellbeing.satiety, 79)
        self.assertEqual(completed.record.state.decay_progress.satiety_seconds, 0)
        self.assertEqual(completed.record.revision, 2)
        self.assertEqual(len(history), 2)

    async def test_clock_rollback_does_not_commit_or_move_baseline(self) -> None:
        service = PetStateService(self._repository, self._clock)
        initialized = await service.initialize()
        self._clock.advance(timedelta(minutes=-5))

        evaluation = await service.evaluate_runtime()
        reloaded = await self._repository.load()

        self.assertEqual(evaluation.decay_outcome.status, DecayStatus.CLOCK_ROLLBACK)
        self.assertEqual(evaluation.record, initialized.record)
        self.assertEqual(reloaded, initialized.record)

    async def test_floor_evaluations_do_not_duplicate_history(self) -> None:
        floor_state = PetState(
            wellbeing=PetWellbeing(
                satiety=0,
                energy=0,
                attention=0,
                affection=50,
            )
        )
        await self._repository.load_or_create(floor_state, self._clock.now())
        service = PetStateService(self._repository, self._clock)
        await service.initialize()

        self._clock.advance(timedelta(hours=2))
        first = await service.evaluate_runtime()
        self._clock.advance(timedelta(hours=2))
        second = await service.evaluate_runtime()
        history = await self._repository.get_recent_history(10)

        self.assertEqual(first.record.state, floor_state)
        self.assertEqual(second.record.state, floor_state)
        self.assertEqual(second.record.revision, 2)
        self.assertEqual(len(history), 1)

    async def test_concurrent_services_retry_a_stale_revision_once(self) -> None:
        first_service = PetStateService(self._repository, self._clock)
        second_service = PetStateService(self._repository, self._clock)
        await first_service.initialize()
        await second_service.initialize()
        self._clock.advance(timedelta(minutes=45))

        first, second = await asyncio.gather(
            first_service.evaluate_runtime(),
            second_service.evaluate_runtime(),
        )
        persisted = await self._repository.load()

        self.assertIsNotNone(persisted)
        self.assertEqual(first.record.state, second.record.state)
        self.assertEqual(first.record.revision, 1)
        self.assertEqual(second.record.revision, 1)
        self.assertEqual(persisted, first.record)

    async def test_public_service_surface_has_no_text_or_generic_patch_input(
        self,
    ) -> None:
        service = PetStateService(self._repository, self._clock)

        public_callables = {
            name
            for name in dir(service)
            if not name.startswith("_") and callable(getattr(service, name))
        }

        self.assertEqual(
            public_callables,
            {"evaluate_runtime", "initialize", "snapshot"},
        )

    async def test_clock_must_return_an_aware_datetime(self) -> None:
        service = PetStateService(
            self._repository,
            _FakeClock(datetime(2026, 8, 14, 8, 0)),
        )

        with self.assertRaises(ValueError):
            await service.initialize()


class _FakeClock:
    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, elapsed: timedelta) -> None:
        self._current += elapsed


if __name__ == "__main__":
    unittest.main()
