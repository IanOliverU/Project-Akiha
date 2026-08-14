"""Proactive companion suggestion generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from project_akiha.core.behavior.activity import ActivitySnapshot, ActivityState
from project_akiha.core.behavior.notification_policy import (
    NotificationPolicy,
    NotificationRequest,
    NotificationUrgency,
)
from project_akiha.core.pet import PetBandTransition, PetNeed, WellbeingBand


@dataclass(frozen=True, slots=True)
class ProactiveSuggestion:
    """A companion suggestion that passed policy checks."""

    kind: str
    message: str
    urgency: NotificationUrgency
    created_at: datetime
    activity_state: ActivityState
    idle_seconds: int


class ProactiveSuggestionEngine:
    """Generate conservative proactive suggestions from activity state."""

    _idle_check_in_kind = "idle_check_in"
    _idle_check_in_message = (
        "You've been quiet for a bit. Want to stretch or take a short pause?"
    )
    _pet_need_messages = {
        (PetNeed.SATIETY, WellbeingBand.LOW): (
            "I could use something to eat when you have a moment."
        ),
        (PetNeed.SATIETY, WellbeingBand.CRITICAL): (
            "I'm very hungry now. Could you feed me when you're able?"
        ),
        (PetNeed.ENERGY, WellbeingBand.LOW): (
            "I'm feeling a little tired. Could I rest for a while?"
        ),
        (PetNeed.ENERGY, WellbeingBand.CRITICAL): (
            "My energy is very low. May I rest for a while?"
        ),
        (PetNeed.ATTENTION, WellbeingBand.LOW): (
            "Could we spend a little time together when you're free?"
        ),
        (PetNeed.ATTENTION, WellbeingBand.CRITICAL): (
            "I've been missing you. Could we spend some time together?"
        ),
    }

    def __init__(self, notification_policy: NotificationPolicy) -> None:
        self._notification_policy = notification_policy
        self._last_suggestion_at: datetime | None = None

    @property
    def last_suggestion_at(self) -> datetime | None:
        """Return when the last suggestion passed policy checks."""
        return self._last_suggestion_at

    def evaluate_activity(
        self,
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Return an allowed suggestion for the activity snapshot, if any."""
        current_time = now or datetime.now(tz=UTC)
        request = self._request_for_activity(activity)
        if request is None:
            return None

        decision = self._notification_policy.evaluate(
            request,
            activity=activity,
            now=current_time,
            last_notification_at=self._last_suggestion_at,
        )
        if not decision.allowed:
            return None

        self._last_suggestion_at = current_time
        return ProactiveSuggestion(
            kind=request.kind,
            message=request.message,
            urgency=request.urgency,
            created_at=current_time,
            activity_state=activity.state,
            idle_seconds=activity.idle_seconds,
        )

    def evaluate_pet_transition(
        self,
        transition: PetBandTransition,
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Return one edge-triggered, policy-gated pet-need suggestion."""
        if not isinstance(transition, PetBandTransition):
            raise TypeError("transition must be a PetBandTransition value.")
        current_time = now or datetime.now(tz=UTC)
        message = self._pet_need_messages.get(
            (transition.need, transition.current_band)
        )
        if message is None or _is_recovery(transition):
            return None

        request = NotificationRequest(
            kind=(f"pet_need_{transition.need.value}_{transition.current_band.value}"),
            message=message,
            urgency=(
                NotificationUrgency.NORMAL
                if transition.current_band is WellbeingBand.CRITICAL
                else NotificationUrgency.LOW
            ),
        )
        decision = self._notification_policy.evaluate(
            request,
            activity=activity,
            now=current_time,
            last_notification_at=self._last_suggestion_at,
        )
        if not decision.allowed:
            return None

        self._last_suggestion_at = current_time
        return ProactiveSuggestion(
            kind=request.kind,
            message=request.message,
            urgency=request.urgency,
            created_at=current_time,
            activity_state=activity.state,
            idle_seconds=activity.idle_seconds,
        )

    def _request_for_activity(
        self,
        activity: ActivitySnapshot,
    ) -> NotificationRequest | None:
        if activity.state != ActivityState.IDLE:
            return None

        return NotificationRequest(
            kind=self._idle_check_in_kind,
            message=self._idle_check_in_message,
            urgency=NotificationUrgency.LOW,
        )


def _is_recovery(transition: PetBandTransition) -> bool:
    ranks = {
        WellbeingBand.CRITICAL: 0,
        WellbeingBand.LOW: 1,
        WellbeingBand.STABLE: 2,
    }
    return ranks[transition.current_band] > ranks[transition.previous_band]
