"""Typed contracts for bounded autonomous desktop-pet activities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum

from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.pet import PetState
from project_akiha.core.state.animation import AnimationState

AUTONOMOUS_ACTIVITY_SOURCE = "autonomous_activity"


class PetActivityId(StrEnum):
    """Closed autonomous activities supported by approved Phase 10 assets."""

    QUIET_IDLE = "quiet_idle"
    WANDER = "wander"
    REST = "rest"


class PetActivityPriority(IntEnum):
    """Preemption order for animation-owning companion behavior."""

    AUTONOMOUS = 10
    CARE_REACTION = 20
    DIRECT_CONTROL = 30
    VOICE = 40
    DRAG = 50


class PetActivityCancellationReason(StrEnum):
    """Privacy-safe reasons an autonomous activity may end early."""

    USER_ACTIVITY = "user_activity"
    DIRECT_CONTROL = "direct_control"
    CARE_INTERACTION = "care_interaction"
    VOICE_ACTIVITY = "voice_activity"
    DRAG_STARTED = "drag_started"
    CONTEXT_CHANGED = "context_changed"
    DISABLED = "disabled"
    TRANSITION_REJECTED = "transition_rejected"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class PetActivityDefinition:
    """One trusted activity mapped to an existing animation state."""

    activity_id: PetActivityId
    animation_state: AnimationState
    duration_seconds: int
    cooldown_seconds: int
    selection_priority: int
    allowed_user_states: frozenset[ActivityState]
    allowed_moods: frozenset[CompanionMood]
    minimum_energy: int = 0
    maximum_energy: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.activity_id, PetActivityId):
            raise TypeError("activity_id must be a PetActivityId value.")
        if not isinstance(self.animation_state, AnimationState):
            raise TypeError("animation_state must be an AnimationState value.")
        expected_state = {
            PetActivityId.QUIET_IDLE: AnimationState.IDLE,
            PetActivityId.WANDER: AnimationState.WALKING,
            PetActivityId.REST: AnimationState.SLEEPING,
        }[self.activity_id]
        if self.animation_state is not expected_state:
            raise ValueError("activity animation_state does not match its closed ID.")
        _require_positive_int(self.duration_seconds, "duration_seconds")
        _require_nonnegative_int(self.cooldown_seconds, "cooldown_seconds")
        _require_nonnegative_int(self.selection_priority, "selection_priority")
        if not self.allowed_user_states or any(
            not isinstance(value, ActivityState) for value in self.allowed_user_states
        ):
            raise ValueError("allowed_user_states must contain typed values.")
        if not self.allowed_moods or any(
            not isinstance(value, CompanionMood) for value in self.allowed_moods
        ):
            raise ValueError("allowed_moods must contain typed values.")
        _require_percentage(self.minimum_energy, "minimum_energy")
        _require_percentage(self.maximum_energy, "maximum_energy")
        if self.minimum_energy > self.maximum_energy:
            raise ValueError("minimum_energy cannot exceed maximum_energy.")


@dataclass(frozen=True, slots=True)
class PetActivityContext:
    """Structured local inputs used for deterministic activity selection."""

    now: datetime
    user_activity: ActivityState
    mood: CompanionMood
    pet_state: PetState
    animation_state: AnimationState

    def __post_init__(self) -> None:
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("activity context time must be timezone-aware.")
        if not isinstance(self.user_activity, ActivityState):
            raise TypeError("user_activity must be an ActivityState value.")
        if not isinstance(self.mood, CompanionMood):
            raise TypeError("mood must be a CompanionMood value.")
        if not isinstance(self.pet_state, PetState):
            raise TypeError("pet_state must be a PetState value.")
        if not isinstance(self.animation_state, AnimationState):
            raise TypeError("animation_state must be an AnimationState value.")


@dataclass(frozen=True, slots=True)
class PetActivityDecision:
    """One deterministic scheduler decision and its bounded reason."""

    definition: PetActivityDefinition | None
    reason: str


@dataclass(frozen=True, slots=True)
class PetActivitySession:
    """One in-memory autonomous activity lifecycle."""

    definition: PetActivityDefinition
    started_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.definition, PetActivityDefinition):
            raise TypeError("definition must be a PetActivityDefinition value.")
        for value in (self.started_at, self.ends_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("activity session times must be timezone-aware.")
        if self.ends_at <= self.started_at:
            raise ValueError("activity session must have a positive duration.")


def _require_nonnegative_int(value: int, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer.")


def _require_positive_int(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer.")


def _require_percentage(value: int, name: str) -> None:
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError(f"{name} must be an integer from 0 through 100.")
