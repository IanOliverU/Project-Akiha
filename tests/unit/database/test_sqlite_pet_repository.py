"""Tests for revisioned SQLite pet-state persistence."""

from __future__ import annotations

import sqlite3
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.pet import (
    DecayMode,
    PetMutationKind,
    PetState,
    PetStateConflictError,
    evaluate_elapsed_decay,
)
from project_akiha.database import SQLitePetStateRepository


class SQLitePetStateRepositoryTest(unittest.IsolatedAsyncioTestCase):
    """Verify singleton state, history, and compare-and-swap behavior."""

    async def asyncSetUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self._database_path = Path(self._temporary_directory.name) / "akiha.sqlite3"
        self._repository = SQLitePetStateRepository(self._database_path)
        self._started_at = datetime(2026, 8, 14, 8, 0, tzinfo=UTC)

    async def test_load_or_create_persists_singleton_and_initial_history(self) -> None:
        initial = PetState.initial()

        first = await self._repository.load_or_create(initial, self._started_at)
        second = await self._repository.load_or_create(
            replace(initial, wellbeing=replace(initial.wellbeing, satiety=1)),
            self._started_at + timedelta(hours=1),
        )
        history = await self._repository.get_recent_history(10)

        self.assertEqual(first, second)
        self.assertEqual(first.state, initial)
        self.assertEqual(first.revision, 0)
        self.assertEqual(first.evaluated_at, self._started_at)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].mutation_kind, PetMutationKind.INITIALIZED)
        self.assertIsNone(history[0].previous_state)
        self.assertEqual(history[0].current_state, initial)
        self.assertEqual(history[0].revision, 0)

    async def test_save_transition_round_trips_state_and_history(self) -> None:
        record = await self._repository.load_or_create(
            PetState.initial(),
            self._started_at,
        )
        evaluated_at = self._started_at + timedelta(hours=46)
        outcome = evaluate_elapsed_decay(
            record.state,
            timedelta(hours=46),
            mode=DecayMode.RUNTIME,
        )

        saved = await self._repository.save_transition(
            expected_revision=record.revision,
            previous_state=record.state,
            current_state=outcome.current_state,
            evaluated_at=evaluated_at,
            mutation_kind=PetMutationKind.RUNTIME_DECAY,
            band_transitions=outcome.band_transitions,
            record_history=True,
        )
        reloaded = await self._repository.load()
        history = await self._repository.get_recent_history(10)

        self.assertEqual(saved, reloaded)
        self.assertEqual(saved.revision, 1)
        self.assertEqual(saved.evaluated_at, evaluated_at)
        self.assertEqual(saved.state, outcome.current_state)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].revision, 1)
        self.assertEqual(history[0].previous_state, record.state)
        self.assertEqual(history[0].current_state, outcome.current_state)
        self.assertEqual(history[0].band_transitions, outcome.band_transitions)

    async def test_transition_can_advance_remainders_without_history_noise(
        self,
    ) -> None:
        record = await self._repository.load_or_create(
            PetState.initial(),
            self._started_at,
        )
        outcome = evaluate_elapsed_decay(record.state, timedelta(minutes=5))

        saved = await self._repository.save_transition(
            expected_revision=record.revision,
            previous_state=record.state,
            current_state=outcome.current_state,
            evaluated_at=self._started_at + timedelta(minutes=5),
            mutation_kind=PetMutationKind.RUNTIME_DECAY,
            record_history=False,
        )
        history = await self._repository.get_recent_history(10)

        self.assertEqual(saved.revision, 1)
        self.assertEqual(saved.state.decay_progress.satiety_seconds, 300)
        self.assertEqual(len(history), 1)

    async def test_rejects_stale_revision_and_mismatched_previous_state(self) -> None:
        record = await self._repository.load_or_create(
            PetState.initial(),
            self._started_at,
        )
        changed = replace(
            record.state,
            wellbeing=replace(record.state.wellbeing, satiety=79),
        )

        with self.assertRaises(PetStateConflictError):
            await self._repository.save_transition(
                expected_revision=1,
                previous_state=record.state,
                current_state=changed,
                evaluated_at=self._started_at + timedelta(minutes=45),
                mutation_kind=PetMutationKind.RUNTIME_DECAY,
                record_history=True,
            )

        with self.assertRaises(PetStateConflictError):
            await self._repository.save_transition(
                expected_revision=0,
                previous_state=changed,
                current_state=record.state,
                evaluated_at=self._started_at + timedelta(minutes=45),
                mutation_kind=PetMutationKind.RUNTIME_DECAY,
                record_history=True,
            )

    async def test_schema_rejects_invalid_wellbeing_values(self) -> None:
        await self._repository.load_or_create(PetState.initial(), self._started_at)

        connection = sqlite3.connect(self._database_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE pet_state SET satiety = 101 WHERE id = 1")
                connection.commit()
        finally:
            connection.close()

    async def test_argument_validation_rejects_untyped_inputs(self) -> None:
        with self.assertRaises(TypeError):
            await self._repository.load_or_create(  # type: ignore[arg-type]
                "dialogue",
                self._started_at,
            )
        with self.assertRaises(ValueError):
            await self._repository.load_or_create(
                PetState.initial(),
                datetime(2026, 8, 14, 8, 0),
            )
        with self.assertRaises(TypeError):
            await self._repository.get_recent_history(True)


if __name__ == "__main__":
    unittest.main()
