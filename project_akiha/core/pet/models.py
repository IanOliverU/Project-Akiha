"""Immutable domain models for Akiha's pet state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_MINIMUM_WELLBEING = 0
_MAXIMUM_WELLBEING = 100


class WellbeingBand(StrEnum):
    """User-facing wellbeing thresholds, ordered from least to most healthy."""

    CRITICAL = "critical"
    LOW = "low"
    STABLE = "stable"


class PetNeed(StrEnum):
    """Immediate care values that may decay and request attention."""

    SATIETY = "satiety"
    ENERGY = "energy"
    ATTENTION = "attention"


class CareAction(StrEnum):
    """Explicit care actions accepted by the future pet-state service."""

    FEED = "feed"
    REST = "rest"
    SPEND_TIME = "spend_time"


class PetInteractionKind(StrEnum):
    """Approved structured interactions that may later grant progression."""

    CONVERSATION_COMPLETED = "conversation_completed"


class DecayMode(StrEnum):
    """Whether elapsed decay occurred during runtime or while the app was closed."""

    RUNTIME = "runtime"
    OFFLINE_CATCH_UP = "offline_catch_up"


class DecayStatus(StrEnum):
    """Bounded diagnostic result from one pure decay evaluation."""

    APPLIED = "applied"
    NO_ELAPSED_TIME = "no_elapsed_time"
    CLOCK_ROLLBACK = "clock_rollback"


class PetMutationKind(StrEnum):
    """Typed causes that may be persisted in pet-state history."""

    INITIALIZED = "initialized"
    RUNTIME_DECAY = "runtime_decay"
    OFFLINE_CATCH_UP = "offline_catch_up"
    CARE_FEED = "care_feed"
    CARE_REST = "care_rest"
    CARE_SPEND_TIME = "care_spend_time"


@dataclass(frozen=True, slots=True)
class PetWellbeing:
    """Positive wellbeing values where a higher number is healthier."""

    satiety: int = 80
    energy: int = 80
    attention: int = 70
    affection: int = 50

    def __post_init__(self) -> None:
        _require_bounded_int(self.satiety, "satiety")
        _require_bounded_int(self.energy, "energy")
        _require_bounded_int(self.attention, "attention")
        _require_bounded_int(self.affection, "affection")

    def value_for(self, need: PetNeed) -> int:
        """Return one immediate care value without dynamic attribute access."""
        if need is PetNeed.SATIETY:
            return self.satiety
        if need is PetNeed.ENERGY:
            return self.energy
        if need is PetNeed.ATTENTION:
            return self.attention
        raise TypeError("need must be a PetNeed value.")

    def band_for(self, need: PetNeed) -> WellbeingBand:
        """Return the current threshold band for one immediate need."""
        return wellbeing_band(self.value_for(need))


@dataclass(frozen=True, slots=True)
class PetProgression:
    """Validated progression totals; level derivation is finalized later."""

    xp: int = 0
    level: int = 1
    currency: int = 0

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.xp, "xp")
        _require_positive_int(self.level, "level")
        _require_nonnegative_int(self.currency, "currency")


@dataclass(frozen=True, slots=True)
class PetDecayProgress:
    """Unconsumed elapsed seconds carried between deterministic evaluations."""

    satiety_seconds: int = 0
    energy_seconds: int = 0
    attention_seconds: int = 0

    def __post_init__(self) -> None:
        _require_nonnegative_int(self.satiety_seconds, "satiety remainder")
        _require_nonnegative_int(self.energy_seconds, "energy remainder")
        _require_nonnegative_int(self.attention_seconds, "attention remainder")

    def seconds_for(self, need: PetNeed) -> int:
        """Return one need's unconsumed elapsed seconds."""
        if need is PetNeed.SATIETY:
            return self.satiety_seconds
        if need is PetNeed.ENERGY:
            return self.energy_seconds
        if need is PetNeed.ATTENTION:
            return self.attention_seconds
        raise TypeError("need must be a PetNeed value.")


@dataclass(frozen=True, slots=True)
class PetState:
    """Complete framework-free aggregate owned by the future pet-state service."""

    wellbeing: PetWellbeing = field(default_factory=PetWellbeing)
    progression: PetProgression = field(default_factory=PetProgression)
    decay_progress: PetDecayProgress = field(default_factory=PetDecayProgress)

    def __post_init__(self) -> None:
        if not isinstance(self.wellbeing, PetWellbeing):
            raise TypeError("wellbeing must be a PetWellbeing value.")
        if not isinstance(self.progression, PetProgression):
            raise TypeError("progression must be a PetProgression value.")
        if not isinstance(self.decay_progress, PetDecayProgress):
            raise TypeError("decay_progress must be a PetDecayProgress value.")

    @classmethod
    def initial(cls) -> PetState:
        """Return the approved gentle-profile initial state."""
        return cls()


@dataclass(frozen=True, slots=True)
class PetInteractionEvent:
    """A language-neutral interaction eligible for future progression rules."""

    event_id: UUID
    kind: PetInteractionKind
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, UUID):
            raise TypeError("interaction event_id must be a UUID.")
        if not isinstance(self.kind, PetInteractionKind):
            raise TypeError("interaction kind must be a PetInteractionKind value.")
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("interaction occurred_at must be a datetime.")
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("interaction occurred_at must be timezone-aware.")


@dataclass(frozen=True, slots=True)
class PetBandTransition:
    """One adjacent threshold edge crossed by an immediate care value."""

    need: PetNeed
    previous_band: WellbeingBand
    current_band: WellbeingBand

    def __post_init__(self) -> None:
        if not isinstance(self.need, PetNeed):
            raise TypeError("transition need must be a PetNeed value.")
        if not isinstance(self.previous_band, WellbeingBand) or not isinstance(
            self.current_band, WellbeingBand
        ):
            raise TypeError("transition bands must be WellbeingBand values.")
        if self.previous_band is self.current_band:
            raise ValueError("a band transition must cross a threshold.")
        if abs(_band_rank(self.previous_band) - _band_rank(self.current_band)) != 1:
            raise ValueError("a band transition must represent one adjacent edge.")


@dataclass(frozen=True, slots=True)
class PetDecayPolicy:
    """Explicit intervals and offline cap used by pure decay evaluation."""

    satiety_interval_seconds: int = 45 * 60
    energy_interval_seconds: int = 60 * 60
    attention_interval_seconds: int = 90 * 60
    offline_cap_seconds: int = 12 * 60 * 60

    def __post_init__(self) -> None:
        _require_positive_int(self.satiety_interval_seconds, "satiety interval")
        _require_positive_int(self.energy_interval_seconds, "energy interval")
        _require_positive_int(self.attention_interval_seconds, "attention interval")
        _require_positive_int(self.offline_cap_seconds, "offline cap")

    def interval_for(self, need: PetNeed) -> int:
        """Return the configured interval for one decaying need."""
        if need is PetNeed.SATIETY:
            return self.satiety_interval_seconds
        if need is PetNeed.ENERGY:
            return self.energy_interval_seconds
        if need is PetNeed.ATTENTION:
            return self.attention_interval_seconds
        raise TypeError("need must be a PetNeed value.")


@dataclass(frozen=True, slots=True)
class PetDecayOutcome:
    """Deterministic result and threshold edges from one elapsed-time evaluation."""

    previous_state: PetState
    current_state: PetState
    mode: DecayMode
    status: DecayStatus
    requested_elapsed_seconds: int
    applied_elapsed_seconds: int
    was_capped: bool
    band_transitions: tuple[PetBandTransition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.previous_state, PetState) or not isinstance(
            self.current_state, PetState
        ):
            raise TypeError("decay outcome states must be PetState values.")
        if not isinstance(self.mode, DecayMode):
            raise TypeError("decay outcome mode must be a DecayMode value.")
        if not isinstance(self.status, DecayStatus):
            raise TypeError("decay outcome status must be a DecayStatus value.")
        _require_exact_int(
            self.requested_elapsed_seconds,
            "requested elapsed seconds",
        )
        _require_nonnegative_int(
            self.applied_elapsed_seconds,
            "applied elapsed seconds",
        )
        if not isinstance(self.was_capped, bool):
            raise TypeError("was_capped must be a boolean.")
        if any(
            not isinstance(transition, PetBandTransition)
            for transition in self.band_transitions
        ):
            raise TypeError("band_transitions must contain PetBandTransition values.")

    @property
    def wellbeing_changed(self) -> bool:
        """Return whether one or more visible wellbeing values changed."""
        return self.previous_state.wellbeing != self.current_state.wellbeing


@dataclass(frozen=True, slots=True)
class PetCareOutcome:
    """Deterministic result of one explicit typed care action."""

    action: CareAction
    previous_state: PetState
    current_state: PetState
    band_transitions: tuple[PetBandTransition, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.action, CareAction):
            raise TypeError("care outcome action must be a CareAction value.")
        if not isinstance(self.previous_state, PetState) or not isinstance(
            self.current_state, PetState
        ):
            raise TypeError("care outcome states must be PetState values.")
        if any(
            not isinstance(transition, PetBandTransition)
            for transition in self.band_transitions
        ):
            raise TypeError("care transitions must be PetBandTransition values.")

    @property
    def changed(self) -> bool:
        """Return whether the action changed any validated pet-state value."""
        return self.previous_state != self.current_state


@dataclass(frozen=True, slots=True)
class PetStateRecord:
    """Revisioned persisted pet state and its elapsed-time baseline."""

    state: PetState
    revision: int
    evaluated_at: datetime
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.state, PetState):
            raise TypeError("pet-state record state must be a PetState value.")
        _require_nonnegative_int(self.revision, "pet-state revision")
        _require_aware_datetime(self.evaluated_at, "pet-state evaluated_at")
        _require_aware_datetime(self.created_at, "pet-state created_at")
        _require_aware_datetime(self.updated_at, "pet-state updated_at")


@dataclass(frozen=True, slots=True)
class PetStateHistoryEntry:
    """One typed, local-only record of a committed pet-state transition."""

    id: int
    revision: int
    mutation_kind: PetMutationKind
    previous_state: PetState | None
    current_state: PetState
    band_transitions: tuple[PetBandTransition, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        _require_positive_int(self.id, "pet-state history id")
        _require_nonnegative_int(self.revision, "pet-state history revision")
        if not isinstance(self.mutation_kind, PetMutationKind):
            raise TypeError("history mutation_kind must be a PetMutationKind value.")
        if self.previous_state is not None and not isinstance(
            self.previous_state, PetState
        ):
            raise TypeError("history previous_state must be a PetState or None.")
        if not isinstance(self.current_state, PetState):
            raise TypeError("history current_state must be a PetState value.")
        if any(
            not isinstance(transition, PetBandTransition)
            for transition in self.band_transitions
        ):
            raise TypeError("history transitions must be PetBandTransition values.")
        _require_aware_datetime(self.created_at, "pet-state history created_at")


@dataclass(frozen=True, slots=True)
class PetStateEvaluation:
    """Service result containing the durable record and pure decay outcome."""

    record: PetStateRecord
    decay_outcome: PetDecayOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.record, PetStateRecord):
            raise TypeError("evaluation record must be a PetStateRecord value.")
        if not isinstance(self.decay_outcome, PetDecayOutcome):
            raise TypeError("evaluation outcome must be a PetDecayOutcome value.")
        if self.record.state != self.decay_outcome.current_state:
            raise ValueError("evaluation record must contain the outcome state.")


@dataclass(frozen=True, slots=True)
class PetCareEvaluation:
    """Service result containing the durable record and pure care outcome."""

    record: PetStateRecord
    care_outcome: PetCareOutcome

    def __post_init__(self) -> None:
        if not isinstance(self.record, PetStateRecord):
            raise TypeError("care evaluation record must be a PetStateRecord value.")
        if not isinstance(self.care_outcome, PetCareOutcome):
            raise TypeError("care evaluation outcome must be a PetCareOutcome value.")
        if self.record.state != self.care_outcome.current_state:
            raise ValueError("care evaluation record must contain the outcome state.")


def wellbeing_band(value: int) -> WellbeingBand:
    """Return the approved edge-inclusive band for a wellbeing value."""
    _require_bounded_int(value, "wellbeing value")
    if value <= 25:
        return WellbeingBand.CRITICAL
    if value <= 50:
        return WellbeingBand.LOW
    return WellbeingBand.STABLE


def _band_rank(band: WellbeingBand) -> int:
    if band is WellbeingBand.CRITICAL:
        return 0
    if band is WellbeingBand.LOW:
        return 1
    if band is WellbeingBand.STABLE:
        return 2
    raise TypeError("band must be a WellbeingBand value.")


def _require_bounded_int(value: int, label: str) -> None:
    _require_exact_int(value, label)
    if not _MINIMUM_WELLBEING <= value <= _MAXIMUM_WELLBEING:
        raise ValueError(f"{label} must be between 0 and 100.")


def _require_nonnegative_int(value: int, label: str) -> None:
    _require_exact_int(value, label)
    if value < 0:
        raise ValueError(f"{label} cannot be negative.")


def _require_positive_int(value: int, label: str) -> None:
    _require_exact_int(value, label)
    if value <= 0:
        raise ValueError(f"{label} must be positive.")


def _require_exact_int(value: int, label: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer.")


def _require_aware_datetime(value: datetime, label: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{label} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
