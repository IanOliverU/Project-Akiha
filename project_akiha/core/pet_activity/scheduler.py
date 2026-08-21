"""Deterministic selection for bounded autonomous pet activities."""

from __future__ import annotations

from datetime import datetime, timedelta

from project_akiha.core.pet_activity.models import (
    PetActivityContext,
    PetActivityDecision,
    PetActivityDefinition,
    PetActivityId,
)
from project_akiha.core.state.animation import AnimationState


class PetActivityScheduler:
    """Choose eligible activities without randomness, dialogue, or providers."""

    def __init__(self, definitions: tuple[PetActivityDefinition, ...]) -> None:
        if any(not isinstance(value, PetActivityDefinition) for value in definitions):
            raise TypeError("definitions must contain PetActivityDefinition values.")
        self._definitions = definitions
        self._last_finished_at: dict[PetActivityId, datetime] = {}

    def select(self, context: PetActivityContext) -> PetActivityDecision:
        """Select one eligible definition with stable ordering and cooldowns."""
        if not isinstance(context, PetActivityContext):
            raise TypeError("context must be a PetActivityContext value.")
        if context.animation_state is not AnimationState.IDLE:
            return PetActivityDecision(None, "animation_busy")

        eligible = tuple(
            definition
            for definition in self._definitions
            if self.is_eligible(definition, context)
        )
        if not eligible:
            return PetActivityDecision(None, "no_eligible_activity")

        definition = min(
            eligible,
            key=lambda value: (
                -value.selection_priority,
                self._last_finished_at.get(
                    value.activity_id, datetime.min.replace(tzinfo=context.now.tzinfo)
                ),
                value.activity_id.value,
            ),
        )
        return PetActivityDecision(definition, "selected")

    def mark_finished(self, activity_id: PetActivityId, finished_at: datetime) -> None:
        """Start one cooldown after completion or cancellation."""
        if not isinstance(activity_id, PetActivityId):
            raise TypeError("activity_id must be a PetActivityId value.")
        if finished_at.tzinfo is None or finished_at.utcoffset() is None:
            raise ValueError("finished_at must be timezone-aware.")
        self._last_finished_at[activity_id] = finished_at

    def is_eligible(
        self,
        definition: PetActivityDefinition,
        context: PetActivityContext,
    ) -> bool:
        """Return whether structured context permits one activity."""
        if not isinstance(definition, PetActivityDefinition):
            raise TypeError("definition must be a PetActivityDefinition value.")
        if not isinstance(context, PetActivityContext):
            raise TypeError("context must be a PetActivityContext value.")
        if context.user_activity not in definition.allowed_user_states:
            return False
        if context.mood not in definition.allowed_moods:
            return False
        energy = context.pet_state.wellbeing.energy
        if not definition.minimum_energy <= energy <= definition.maximum_energy:
            return False
        last_finished = self._last_finished_at.get(definition.activity_id)
        if last_finished is None:
            return True
        return context.now >= last_finished + timedelta(
            seconds=definition.cooldown_seconds
        )
