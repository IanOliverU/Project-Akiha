"""Privacy-safe diagnostics for the durable pet-state subsystem."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from project_akiha.core.pet import PetStateRecord


@dataclass(frozen=True, slots=True)
class PetDiagnosticsSnapshot:
    """Bounded operational metadata with no dialogue or provider content."""

    revision: int
    evaluated_at: datetime
    satiety: int
    energy: int
    attention: int
    affection: int
    xp: int
    level: int
    currency: int
    decay_remainders: tuple[int, int, int]

    @property
    def state_summary(self) -> str:
        """Render the four validated wellbeing values."""
        return (
            f"Satiety {self.satiety}% | Energy {self.energy}% | "
            f"Attention {self.attention}% | Affection {self.affection}%"
        )

    @property
    def progression_summary(self) -> str:
        """Render bounded progression totals."""
        return f"Level {self.level} | {self.xp} XP | {self.currency} currency"

    @property
    def runtime_summary(self) -> str:
        """Render revision and elapsed-decay remainder diagnostics."""
        satiety, energy, attention = self.decay_remainders
        return (
            f"Revision {self.revision} | Remainders: "
            f"satiety {satiety}s, energy {energy}s, attention {attention}s"
        )


def build_pet_diagnostics(record: PetStateRecord) -> PetDiagnosticsSnapshot:
    """Build diagnostics from one already-validated persistent record."""
    if not isinstance(record, PetStateRecord):
        raise TypeError("record must be a PetStateRecord value.")
    state = record.state
    wellbeing = state.wellbeing
    progression = state.progression
    decay = state.decay_progress
    return PetDiagnosticsSnapshot(
        revision=record.revision,
        evaluated_at=record.evaluated_at,
        satiety=wellbeing.satiety,
        energy=wellbeing.energy,
        attention=wellbeing.attention,
        affection=wellbeing.affection,
        xp=progression.xp,
        level=progression.level,
        currency=progression.currency,
        decay_remainders=(
            decay.satiety_seconds,
            decay.energy_seconds,
            decay.attention_seconds,
        ),
    )
