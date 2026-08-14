"""Typed pet-state foundation and language-neutral domain rules."""

from project_akiha.core.pet.models import (
    CareAction,
    DecayMode,
    DecayStatus,
    PetBandTransition,
    PetDecayOutcome,
    PetDecayPolicy,
    PetDecayProgress,
    PetInteractionEvent,
    PetInteractionKind,
    PetMutationKind,
    PetNeed,
    PetProgression,
    PetState,
    PetStateEvaluation,
    PetStateHistoryEntry,
    PetStateRecord,
    PetWellbeing,
    WellbeingBand,
    wellbeing_band,
)
from project_akiha.core.pet.repository import (
    PetStateConflictError,
    PetStateRepository,
)
from project_akiha.core.pet.rules import (
    DEFAULT_DECAY_POLICY,
    collect_band_transitions,
    evaluate_elapsed_decay,
)

__all__ = [
    "DEFAULT_DECAY_POLICY",
    "CareAction",
    "DecayMode",
    "DecayStatus",
    "PetBandTransition",
    "PetDecayOutcome",
    "PetDecayPolicy",
    "PetDecayProgress",
    "PetInteractionEvent",
    "PetInteractionKind",
    "PetMutationKind",
    "PetNeed",
    "PetProgression",
    "PetState",
    "PetStateConflictError",
    "PetStateEvaluation",
    "PetStateHistoryEntry",
    "PetStateRecord",
    "PetStateRepository",
    "PetWellbeing",
    "WellbeingBand",
    "collect_band_transitions",
    "evaluate_elapsed_decay",
    "wellbeing_band",
]
