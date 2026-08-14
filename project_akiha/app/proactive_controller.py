"""Application-level proactive suggestion wiring."""

from __future__ import annotations

from datetime import datetime, timedelta

from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    ProactiveSuggestion,
    ProactiveSuggestionEngine,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import PetBandTransition, PetNeed, WellbeingBand


class ProactiveController:
    """Evaluate activity state changes and publish allowed suggestions."""

    def __init__(
        self,
        event_bus: EventBus,
        suggestion_engine: ProactiveSuggestionEngine,
    ) -> None:
        self._event_bus = event_bus
        self._suggestion_engine = suggestion_engine
        event_bus.subscribe(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            self._handle_activity_state_changed,
        )

    def evaluate_snapshot(
        self,
        snapshot: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Evaluate an activity snapshot and publish any allowed suggestion."""
        suggestion = self._suggestion_engine.evaluate_activity(snapshot, now)
        if suggestion is not None:
            self._publish_suggestion(suggestion)
        return suggestion

    def evaluate_pet_transitions(
        self,
        transitions: tuple[PetBandTransition, ...],
        activity: ActivitySnapshot,
        now: datetime | None = None,
    ) -> ProactiveSuggestion | None:
        """Publish typed pet edges and at most one policy-gated suggestion."""
        if not isinstance(transitions, tuple) or any(
            not isinstance(transition, PetBandTransition) for transition in transitions
        ):
            raise TypeError("transitions must be a tuple of PetBandTransition values.")
        if not isinstance(activity, ActivitySnapshot):
            raise TypeError("activity must be an ActivitySnapshot value.")
        if not transitions:
            return None

        selected = _select_pet_transition(transitions)
        for transition in transitions:
            kind = f"pet_need_{transition.need.value}_{transition.current_band.value}"
            self._event_bus.publish(
                EventType.PET_NEED_BAND_CHANGED,
                {
                    "kind": kind,
                    "need": transition.need.value,
                    "previous_band": transition.previous_band.value,
                    "current_band": transition.current_band.value,
                    "selected": transition is selected,
                },
            )

        suggestion = self._suggestion_engine.evaluate_pet_transition(
            selected,
            activity,
            now,
        )
        if suggestion is not None:
            self._publish_suggestion(suggestion)
        return suggestion

    def _handle_activity_state_changed(self, event: Event) -> None:
        snapshot = _snapshot_from_payload(event.payload)
        if snapshot is None:
            return
        self.evaluate_snapshot(
            snapshot,
            snapshot.last_activity_at + timedelta(seconds=snapshot.idle_seconds),
        )

    def _publish_suggestion(self, suggestion: ProactiveSuggestion) -> None:
        self._event_bus.publish(
            EventType.PROACTIVE_SUGGESTION_READY,
            {
                "kind": suggestion.kind,
                "message": suggestion.message,
                "urgency": suggestion.urgency.value,
                "created_at": suggestion.created_at.isoformat(),
                "activity_state": suggestion.activity_state.value,
                "idle_seconds": suggestion.idle_seconds,
            },
        )


def _snapshot_from_payload(payload: dict[str, object]) -> ActivitySnapshot | None:
    state_value = payload.get("state")
    idle_seconds = payload.get("idle_seconds")
    last_activity_at = payload.get("last_activity_at")
    source = payload.get("source")

    if not isinstance(state_value, str):
        return None
    if not isinstance(idle_seconds, int):
        return None
    if not isinstance(last_activity_at, str):
        return None
    if not isinstance(source, str):
        return None

    try:
        state = ActivityState(state_value)
        parsed_last_activity_at = datetime.fromisoformat(last_activity_at)
    except ValueError:
        return None

    return ActivitySnapshot(
        state=state,
        idle_seconds=idle_seconds,
        last_activity_at=parsed_last_activity_at,
        source=source,
    )


def _select_pet_transition(
    transitions: tuple[PetBandTransition, ...],
) -> PetBandTransition:
    band_rank = {
        WellbeingBand.CRITICAL: 0,
        WellbeingBand.LOW: 1,
        WellbeingBand.STABLE: 2,
    }
    need_rank = {
        PetNeed.SATIETY: 0,
        PetNeed.ENERGY: 1,
        PetNeed.ATTENTION: 2,
    }

    def priority(transition: PetBandTransition) -> tuple[int, int, int]:
        recovering = (
            band_rank[transition.current_band] > band_rank[transition.previous_band]
        )
        return (
            1 if recovering else 0,
            (
                -band_rank[transition.current_band]
                if recovering
                else band_rank[transition.current_band]
            ),
            need_rank[transition.need],
        )

    return min(transitions, key=priority)
