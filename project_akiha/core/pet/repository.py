"""Persistence protocol for the single pet-state mutation boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from project_akiha.core.pet.models import (
    PetBandTransition,
    PetMutationKind,
    PetState,
    PetStateHistoryEntry,
    PetStateRecord,
)


class PetStateConflictError(RuntimeError):
    """Raised when a stale revision attempts to overwrite newer pet state."""


class PetStateRepository(Protocol):
    """Load and atomically commit validated pet-state aggregates."""

    async def load_or_create(
        self,
        initial_state: PetState,
        evaluated_at: datetime,
    ) -> PetStateRecord:
        """Return the singleton state, creating it from typed defaults if absent."""

    async def load(self) -> PetStateRecord | None:
        """Return the singleton state when it exists."""

    async def save_transition(
        self,
        *,
        expected_revision: int,
        previous_state: PetState,
        current_state: PetState,
        evaluated_at: datetime,
        mutation_kind: PetMutationKind,
        band_transitions: tuple[PetBandTransition, ...] = (),
        record_history: bool,
    ) -> PetStateRecord:
        """Atomically update one expected revision and optional history row."""

    async def get_recent_history(
        self,
        limit: int,
    ) -> tuple[PetStateHistoryEntry, ...]:
        """Return recent committed pet-state history newest first."""
