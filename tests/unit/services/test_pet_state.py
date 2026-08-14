"""Tests for injected-clock pet-state service orchestration."""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from project_akiha.core.pet import (
    CareAction,
    DecayStatus,
    PetInteractionEvent,
    PetInteractionKind,
    PetMutationKind,
    PetRewardDecision,
    PetState,
    PetWellbeing,
)
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

    async def test_care_actions_commit_typed_history_and_progression(self) -> None:
        service = PetStateService(self._repository, self._clock)
        await service.initialize()

        fed = await service.apply_care_action(CareAction.FEED)
        rested = await service.apply_care_action(CareAction.REST)
        together = await service.apply_care_action(CareAction.SPEND_TIME)
        history = await self._repository.get_recent_history(10)

        self.assertEqual(fed.record.state.wellbeing.satiety, 100)
        self.assertEqual(rested.record.state.wellbeing.energy, 100)
        self.assertEqual(together.record.state.wellbeing.attention, 90)
        self.assertEqual(together.record.state.wellbeing.affection, 51)
        self.assertEqual(together.record.state.progression.xp, 15)
        self.assertEqual(together.record.state.progression.currency, 6)
        self.assertEqual(together.record.state.progression.level, 1)
        self.assertTrue(fed.reward_outcome.granted)
        self.assertTrue(rested.reward_outcome.granted)
        self.assertTrue(together.reward_outcome.granted)
        self.assertEqual(
            tuple(entry.mutation_kind for entry in history[:3]),
            (
                PetMutationKind.CARE_SPEND_TIME,
                PetMutationKind.CARE_REST,
                PetMutationKind.CARE_FEED,
            ),
        )

    async def test_care_recovers_floor_state_and_persists_recovery(self) -> None:
        floor_state = PetState(
            wellbeing=PetWellbeing(
                satiety=0,
                energy=0,
                attention=0,
                affection=0,
            )
        )
        service = PetStateService(
            self._repository,
            self._clock,
            initial_state=floor_state,
        )
        await service.initialize()

        result = await service.apply_care_action(CareAction.FEED)
        reloaded = await self._repository.load()

        self.assertEqual(result.record.state.wellbeing.satiety, 25)
        self.assertEqual(reloaded, result.record)
        self.assertEqual(result.record.revision, 1)

    async def test_fully_capped_care_does_not_write_history_or_revision(self) -> None:
        capped_state = PetState(
            wellbeing=PetWellbeing(
                satiety=100,
                energy=100,
                attention=100,
                affection=100,
            )
        )
        service = PetStateService(
            self._repository,
            self._clock,
            initial_state=capped_state,
        )
        initialized = await service.initialize()

        for action in CareAction:
            result = await service.apply_care_action(action)
            self.assertFalse(result.care_outcome.changed)
            self.assertIs(
                result.reward_outcome.decision,
                PetRewardDecision.NO_STATE_CHANGE,
            )
            self.assertEqual(result.record, initialized.record)

        history = await self._repository.get_recent_history(10)
        self.assertEqual(len(history), 1)

    async def test_care_settles_elapsed_decay_before_applying_recovery(self) -> None:
        service = PetStateService(self._repository, self._clock)
        await service.initialize()
        self._clock.advance(timedelta(minutes=45))

        result = await service.apply_care_action(CareAction.FEED)
        history = await self._repository.get_recent_history(10)

        self.assertEqual(result.care_outcome.previous_state.wellbeing.satiety, 79)
        self.assertEqual(result.record.state.wellbeing.satiety, 100)
        self.assertEqual(result.record.revision, 2)
        self.assertEqual(history[0].mutation_kind, PetMutationKind.CARE_FEED)
        self.assertEqual(history[1].mutation_kind, PetMutationKind.RUNTIME_DECAY)

    async def test_concurrent_care_actions_preserve_both_user_intents(self) -> None:
        initial = PetState(wellbeing=PetWellbeing(satiety=40))
        first_service = PetStateService(
            self._repository,
            self._clock,
            initial_state=initial,
        )
        second_service = PetStateService(
            self._repository,
            self._clock,
            initial_state=initial,
        )
        await first_service.initialize()
        await second_service.initialize()

        first, second = await asyncio.gather(
            first_service.apply_care_action(CareAction.FEED),
            second_service.apply_care_action(CareAction.FEED),
        )
        persisted = await self._repository.load()

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.state.wellbeing.satiety, 90)
        self.assertEqual(persisted.state.progression.xp, 5)
        self.assertEqual(persisted.state.progression.currency, 2)
        self.assertEqual(persisted.revision, 2)
        self.assertEqual({first.record.revision, second.record.revision}, {1, 2})
        self.assertEqual(
            {first.reward_outcome.decision, second.reward_outcome.decision},
            {PetRewardDecision.GRANTED, PetRewardDecision.COOLDOWN},
        )

    async def test_care_cooldown_survives_service_restart(self) -> None:
        initial = PetState(wellbeing=PetWellbeing(satiety=20))
        first_service = PetStateService(
            self._repository,
            self._clock,
            initial_state=initial,
        )
        await first_service.initialize()
        first = await first_service.apply_care_action(CareAction.FEED)

        restarted_repository = SQLitePetStateRepository(self._database_path)
        restarted_service = PetStateService(restarted_repository, self._clock)
        second = await restarted_service.apply_care_action(CareAction.FEED)

        self.assertTrue(first.reward_outcome.granted)
        self.assertEqual(second.record.state.wellbeing.satiety, 70)
        self.assertIs(second.reward_outcome.decision, PetRewardDecision.COOLDOWN)
        self.assertEqual(second.record.state.progression.xp, 5)
        self.assertEqual(second.record.state.progression.currency, 2)

    async def test_conversation_rewards_deduplicate_and_respect_cooldown(self) -> None:
        service = PetStateService(self._repository, self._clock)
        first_event = _conversation_event(self._clock.now())
        first = await service.apply_interaction_event(first_event)
        duplicate = await service.apply_interaction_event(first_event)
        second_event = _conversation_event(self._clock.now())
        cooldown = await service.apply_interaction_event(second_event)
        self._clock.advance(timedelta(minutes=10))
        second = await service.apply_interaction_event(second_event)

        self.assertTrue(first.reward_outcome.granted)
        self.assertIs(
            duplicate.reward_outcome.decision,
            PetRewardDecision.DUPLICATE_EVENT,
        )
        self.assertIs(cooldown.reward_outcome.decision, PetRewardDecision.COOLDOWN)
        self.assertTrue(second.reward_outcome.granted)
        self.assertEqual(second.record.state.progression.xp, 2)
        self.assertEqual(second.record.state.progression.currency, 0)

    async def test_cross_service_duplicate_returns_current_durable_state(self) -> None:
        first_service = PetStateService(self._repository, self._clock)
        second_service = PetStateService(self._repository, self._clock)
        await first_service.initialize()
        await second_service.initialize()
        event = _conversation_event(self._clock.now())

        granted = await first_service.apply_interaction_event(event)
        duplicate = await second_service.apply_interaction_event(event)

        self.assertTrue(granted.reward_outcome.granted)
        self.assertIs(
            duplicate.reward_outcome.decision,
            PetRewardDecision.DUPLICATE_EVENT,
        )
        self.assertEqual(duplicate.record, granted.record)

    async def test_untyped_interaction_is_rejected_before_initialization(self) -> None:
        service = PetStateService(self._repository, self._clock)

        with self.assertRaises(TypeError):
            await service.apply_interaction_event(  # type: ignore[arg-type]
                "conversation completed"
            )

        self.assertIsNone(await self._repository.load())

    async def test_untyped_care_is_rejected_before_state_initialization(self) -> None:
        service = PetStateService(self._repository, self._clock)

        with self.assertRaises(TypeError):
            await service.apply_care_action("feed")  # type: ignore[arg-type]

        self.assertIsNone(await self._repository.load())

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
            {
                "apply_care_action",
                "apply_interaction_event",
                "evaluate_runtime",
                "initialize",
                "snapshot",
            },
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


def _conversation_event(occurred_at: datetime) -> PetInteractionEvent:
    return PetInteractionEvent(
        event_id=uuid4(),
        kind=PetInteractionKind.CONVERSATION_COMPLETED,
        occurred_at=occurred_at,
    )


if __name__ == "__main__":
    unittest.main()
