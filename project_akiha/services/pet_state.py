"""Injected-clock orchestration for the sole pet-state mutation boundary."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol

from project_akiha.core.pet import (
    DEFAULT_DECAY_POLICY,
    DecayMode,
    PetDecayOutcome,
    PetDecayPolicy,
    PetMutationKind,
    PetState,
    PetStateConflictError,
    PetStateEvaluation,
    PetStateRecord,
    PetStateRepository,
    evaluate_elapsed_decay,
)


class PetClock(Protocol):
    """Clock dependency used to keep pet-state evaluation deterministic."""

    def now(self) -> datetime:
        """Return the current timezone-aware timestamp."""


class SystemPetClock:
    """Production UTC clock for the future Phase 9 runtime integration."""

    def now(self) -> datetime:
        """Return the current UTC timestamp."""
        return datetime.now(UTC)


class PetStateService:
    """Apply pure elapsed-time rules and atomically commit validated state."""

    def __init__(
        self,
        repository: PetStateRepository,
        clock: PetClock,
        *,
        initial_state: PetState | None = None,
        decay_policy: PetDecayPolicy = DEFAULT_DECAY_POLICY,
    ) -> None:
        if initial_state is not None and not isinstance(initial_state, PetState):
            raise TypeError("initial_state must be a PetState value or None.")
        if not isinstance(decay_policy, PetDecayPolicy):
            raise TypeError("decay_policy must be a PetDecayPolicy value.")
        self._repository = repository
        self._clock = clock
        self._initial_state = initial_state or PetState.initial()
        self._decay_policy = decay_policy
        self._record: PetStateRecord | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> PetStateEvaluation:
        """Load state and apply at most one bounded offline catch-up interval."""
        async with self._lock:
            now = self._current_time()
            if self._record is None:
                return await self._initialize_locked(now)
            return _unchanged_evaluation(self._record, DecayMode.OFFLINE_CATCH_UP)

    async def snapshot(self) -> PetStateRecord:
        """Return the current durable snapshot without applying runtime decay."""
        async with self._lock:
            if self._record is None:
                await self._initialize_locked(self._current_time())
            return _require_record(self._record)

    async def evaluate_runtime(self) -> PetStateEvaluation:
        """Apply elapsed runtime decay from the last committed UTC baseline."""
        async with self._lock:
            now = self._current_time()
            if self._record is None:
                await self._initialize_locked(now)
            return await self._evaluate_and_commit_locked(now, DecayMode.RUNTIME)

    async def _initialize_locked(self, now: datetime) -> PetStateEvaluation:
        self._record = await self._repository.load_or_create(
            self._initial_state,
            now,
        )
        return await self._evaluate_and_commit_locked(
            now,
            DecayMode.OFFLINE_CATCH_UP,
        )

    async def _evaluate_and_commit_locked(
        self,
        now: datetime,
        mode: DecayMode,
    ) -> PetStateEvaluation:
        record = _require_record(self._record)
        mutation_kind = _mutation_kind_for(mode)

        for attempt in range(2):
            outcome = evaluate_elapsed_decay(
                record.state,
                now - record.evaluated_at,
                mode=mode,
                policy=self._decay_policy,
            )
            if outcome.applied_elapsed_seconds == 0:
                self._record = record
                return PetStateEvaluation(record=record, decay_outcome=outcome)

            try:
                record = await self._repository.save_transition(
                    expected_revision=record.revision,
                    previous_state=record.state,
                    current_state=outcome.current_state,
                    evaluated_at=now,
                    mutation_kind=mutation_kind,
                    band_transitions=outcome.band_transitions,
                    record_history=outcome.wellbeing_changed,
                )
            except PetStateConflictError:
                if attempt == 1:
                    raise
                reloaded = await self._repository.load()
                if reloaded is None:
                    reloaded = await self._repository.load_or_create(
                        self._initial_state,
                        now,
                    )
                record = reloaded
                continue

            self._record = record
            return PetStateEvaluation(record=record, decay_outcome=outcome)

        raise RuntimeError("Pet-state evaluation exhausted its conflict retry.")

    def _current_time(self) -> datetime:
        value = self._clock.now()
        if not isinstance(value, datetime):
            raise TypeError("PetClock.now() must return a datetime.")
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PetClock.now() must return a timezone-aware datetime.")
        return value.astimezone(UTC)


def _mutation_kind_for(mode: DecayMode) -> PetMutationKind:
    if mode is DecayMode.RUNTIME:
        return PetMutationKind.RUNTIME_DECAY
    if mode is DecayMode.OFFLINE_CATCH_UP:
        return PetMutationKind.OFFLINE_CATCH_UP
    raise TypeError("mode must be a DecayMode value.")


def _unchanged_evaluation(
    record: PetStateRecord,
    mode: DecayMode,
) -> PetStateEvaluation:
    outcome: PetDecayOutcome = evaluate_elapsed_decay(
        record.state,
        timedelta(),
        mode=mode,
    )
    return PetStateEvaluation(record=record, decay_outcome=outcome)


def _require_record(record: PetStateRecord | None) -> PetStateRecord:
    if record is None:
        raise RuntimeError("Pet state has not been initialized.")
    return record
