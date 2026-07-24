"""Companion mood state foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from project_akiha.core.behavior.activity import ActivitySnapshot, ActivityState


class CompanionMood(StrEnum):
    """Coarse companion mood states for behavior and animation wiring."""

    CALM = "calm"
    ATTENTIVE = "attentive"
    WAITING = "waiting"
    RESTING = "resting"
    CHECKING_IN = "checking_in"
    SLEEPY = "sleepy"


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
