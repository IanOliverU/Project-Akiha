"""Companion mood state foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from project_akiha.core.behavior.activity import ActivitySnapshot, ActivityState
from project_akiha.core.pet import PetBandTransition, PetNeed, WellbeingBand


class CompanionMood(StrEnum):
    """Coarse companion mood states for behavior and animation wiring."""

    CALM = "calm"
    ATTENTIVE = "attentive"
    WAITING = "waiting"
    RESTING = "resting"
    CHECKING_IN = "checking_in"
    SLEEPY = "sleepy"
    VOICE_LISTENING = "voice_listening"
    VOICE_THINKING = "voice_thinking"
    VOICE_SPEAKING = "voice_speaking"
    VOICE_MUTED = "voice_muted"
    VOICE_ERROR = "voice_error"


@dataclass(frozen=True, slots=True)
class MoodSnapshot:
    """Current companion mood with an explanatory reason."""

    mood: CompanionMood
    reason: str
    updated_at: datetime


class MoodEngine:
    """Derive a conservative companion mood from app behavior signals."""

    def __init__(
        self,
        initial_time: datetime | None = None,
        initial_mood: CompanionMood = CompanionMood.CALM,
    ) -> None:
        self._snapshot = MoodSnapshot(
            mood=initial_mood,
            reason="startup",
            updated_at=initial_time or _now(),
        )

    @property
    def snapshot(self) -> MoodSnapshot:
        """Return the current mood snapshot."""
        return self._snapshot

    def observe_activity(
        self,
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> MoodSnapshot:
        """Update mood from activity state."""
        if activity.state == ActivityState.AWAY:
            return self._transition_to(CompanionMood.RESTING, "user_away", now)
        if activity.state == ActivityState.IDLE:
            return self._transition_to(CompanionMood.WAITING, "user_idle", now)
        return self._transition_to(CompanionMood.ATTENTIVE, activity.source, now)

    def observe_interaction(
        self,
        source: str,
        now: datetime | None = None,
    ) -> MoodSnapshot:
        """Update mood from direct user/app interaction."""
        return self._transition_to(CompanionMood.ATTENTIVE, source, now)

    def observe_sleep_requested(self, now: datetime | None = None) -> MoodSnapshot:
        """Update mood when the user asks Akiha to sleep."""
        return self._transition_to(CompanionMood.SLEEPY, "sleep_requested", now)

    def observe_wake_requested(self, now: datetime | None = None) -> MoodSnapshot:
        """Update mood when the user wakes Akiha."""
        return self._transition_to(CompanionMood.ATTENTIVE, "wake_requested", now)

    def observe_pet_need_transition(
        self,
        transition: PetBandTransition,
        now: datetime | None = None,
    ) -> MoodSnapshot:
        """Reflect one selected structured pet-need transition in mood."""
        if not isinstance(transition, PetBandTransition):
            raise TypeError("transition must be a PetBandTransition value.")

        reason = f"pet_need_{transition.need.value}_{transition.current_band.value}"
        if _is_recovery(transition):
            return self._transition_to(CompanionMood.ATTENTIVE, reason, now)
        if transition.need is PetNeed.ENERGY:
            return self._transition_to(CompanionMood.SLEEPY, reason, now)
        if transition.need is PetNeed.ATTENTION:
            mood = (
                CompanionMood.CHECKING_IN
                if transition.current_band is WellbeingBand.CRITICAL
                else CompanionMood.WAITING
            )
            return self._transition_to(mood, reason, now)
        return self._transition_to(CompanionMood.CHECKING_IN, reason, now)

    def observe_delivery_result(
        self,
        *,
        delivered: bool,
        reason: str,
        now: datetime | None = None,
    ) -> MoodSnapshot:
        """Update mood after a proactive suggestion delivery attempt."""
        if delivered:
            return self._transition_to(CompanionMood.CHECKING_IN, reason, now)
        return self._transition_to(CompanionMood.CALM, reason, now)

    def _transition_to(
        self,
        mood: CompanionMood,
        reason: str,
        now: datetime | None,
    ) -> MoodSnapshot:
        self._snapshot = MoodSnapshot(
            mood=mood,
            reason=reason,
            updated_at=now or _now(),
        )
        return self._snapshot


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _is_recovery(transition: PetBandTransition) -> bool:
    ranks = {
        WellbeingBand.CRITICAL: 0,
        WellbeingBand.LOW: 1,
        WellbeingBand.STABLE: 2,
    }
    return ranks[transition.current_band] > ranks[transition.previous_band]
