"""Application-level companion mood wiring."""

from __future__ import annotations

from datetime import UTC, datetime

from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    CompanionMood,
    MoodEngine,
    MoodSnapshot,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import (
    CareAction,
    PetBandTransition,
    PetNeed,
    WellbeingBand,
)
from project_akiha.core.pet_activity import AUTONOMOUS_ACTIVITY_SOURCE
from project_akiha.core.state.voice import VoiceState


class MoodController:
    """Translate app events into companion mood state changes."""

    _interaction_sources = {
        EventType.CHAT_OPEN_REQUESTED: "chat_open_requested",
        EventType.SETTINGS_OPEN_REQUESTED: "settings_open_requested",
        EventType.PET_DRAG_STARTED: "pet_drag_started",
        EventType.PET_WALK_REQUESTED: "pet_walk_requested",
        EventType.PET_IDLE_REQUESTED: "pet_idle_requested",
        EventType.PET_WAKE_REQUESTED: "pet_wake_requested",
        EventType.PET_STATUS_OPEN_REQUESTED: "pet_status_open_requested",
    }
    _voice_moods = {
        VoiceState.LISTENING: CompanionMood.VOICE_LISTENING,
        VoiceState.THINKING: CompanionMood.VOICE_THINKING,
        VoiceState.SPEAKING: CompanionMood.VOICE_SPEAKING,
        VoiceState.MUTED: CompanionMood.VOICE_MUTED,
        VoiceState.ERROR: CompanionMood.VOICE_ERROR,
    }

    def __init__(
        self,
        event_bus: EventBus,
        mood_engine: MoodEngine,
    ) -> None:
        self._event_bus = event_bus
        self._mood_engine = mood_engine
        self._last_published = mood_engine.snapshot
        self._voice_overlay: VoiceState | None = None

        event_bus.subscribe(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            self._handle_activity_state_changed,
        )
        event_bus.subscribe(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            self._handle_suggestion_delivered,
        )
        event_bus.subscribe(EventType.PET_SLEEP_REQUESTED, self._handle_sleep_requested)
        event_bus.subscribe(
            EventType.PET_NEED_BAND_CHANGED,
            self._handle_pet_need_band_changed,
        )
        event_bus.subscribe(
            EventType.PET_CARE_COMPLETED,
            self._handle_pet_care_completed,
        )
        event_bus.subscribe(EventType.PET_STATE_RESET, self._handle_pet_state_reset)
        event_bus.subscribe(
            EventType.VOICE_STATE_CHANGED,
            self._handle_voice_state_changed,
        )
        for event_type in self._interaction_sources:
            event_bus.subscribe(event_type, self._handle_interaction)

        self._publish_mood(mood_engine.snapshot)

    @property
    def snapshot(self) -> MoodSnapshot:
        """Return the current mood snapshot."""
        return self._mood_engine.snapshot

    def _handle_activity_state_changed(self, event: Event) -> None:
        snapshot = _activity_from_payload(event.payload)
        if snapshot is None:
            return
        self._publish_if_changed(self._mood_engine.observe_activity(snapshot))

    def _handle_suggestion_delivered(self, event: Event) -> None:
        kind = event.payload.get("kind")
        if isinstance(kind, str) and kind.startswith("pet_need_"):
            return
        delivered = event.payload.get("delivered")
        reason = event.payload.get("reason")
        if not isinstance(delivered, bool) or not isinstance(reason, str):
            return
        self._publish_if_changed(
            self._mood_engine.observe_delivery_result(
                delivered=delivered,
                reason=reason,
            )
        )

    def _handle_sleep_requested(self, event: Event) -> None:
        if event.payload.get("source") == AUTONOMOUS_ACTIVITY_SOURCE:
            return
        self._publish_if_changed(self._mood_engine.observe_sleep_requested())

    def _handle_pet_need_band_changed(self, event: Event) -> None:
        if event.payload.get("selected") is not True:
            return
        transition = _pet_transition_from_payload(event.payload)
        if transition is None:
            return
        self._publish_if_changed(
            self._mood_engine.observe_pet_need_transition(transition)
        )

    def _handle_pet_care_completed(self, event: Event) -> None:
        if event.payload.get("changed") is not True:
            return
        action_value = event.payload.get("action")
        level_increased = event.payload.get("level_increased")
        if not isinstance(action_value, str) or not isinstance(level_increased, bool):
            return
        try:
            action = CareAction(action_value)
        except ValueError:
            return
        self._publish_if_changed(
            self._mood_engine.observe_pet_care_completed(
                action,
                level_increased=level_increased,
            )
        )

    def _handle_pet_state_reset(self, event: Event) -> None:
        revision = event.payload.get("revision")
        if type(revision) is not int or revision != 0:
            return
        self._publish_if_changed(
            self._mood_engine.observe_interaction("pet_state_reset")
        )

    def _handle_interaction(self, event: Event) -> None:
        if event.payload.get("source") == AUTONOMOUS_ACTIVITY_SOURCE:
            return
        source = self._interaction_sources[event.event_type]
        if event.event_type == EventType.PET_WAKE_REQUESTED:
            snapshot = self._mood_engine.observe_wake_requested()
        else:
            snapshot = self._mood_engine.observe_interaction(source)
        self._publish_if_changed(snapshot)

    def _handle_voice_state_changed(self, event: Event) -> None:
        state_value = event.payload.get("state")
        if not isinstance(state_value, str):
            return
        try:
            state = VoiceState(state_value)
        except ValueError:
            return

        mood = self._voice_moods.get(state)
        if mood is None:
            self._voice_overlay = None
            self._publish_if_changed(self._mood_engine.snapshot)
            return

        self._voice_overlay = state
        self._publish_mood(
            MoodSnapshot(
                mood=mood,
                reason=f"voice_{state.value}",
                updated_at=datetime.now(tz=UTC),
            )
        )

    def _publish_if_changed(self, snapshot: MoodSnapshot) -> None:
        if self._voice_overlay is not None:
            return
        if (
            snapshot.mood == self._last_published.mood
            and snapshot.reason == self._last_published.reason
        ):
            return
        self._publish_mood(snapshot)

    def _publish_mood(self, snapshot: MoodSnapshot) -> None:
        self._last_published = snapshot
        self._event_bus.publish(
            EventType.MOOD_STATE_CHANGED,
            {
                "mood": snapshot.mood.value,
                "reason": snapshot.reason,
                "updated_at": snapshot.updated_at.isoformat(),
            },
        )


def _activity_from_payload(payload: dict[str, object]) -> ActivitySnapshot | None:
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


def _pet_transition_from_payload(
    payload: dict[str, object],
) -> PetBandTransition | None:
    need_value = payload.get("need")
    previous_band_value = payload.get("previous_band")
    current_band_value = payload.get("current_band")
    if not all(
        isinstance(value, str)
        for value in (need_value, previous_band_value, current_band_value)
    ):
        return None
    try:
        return PetBandTransition(
            need=PetNeed(need_value),
            previous_band=WellbeingBand(previous_band_value),
            current_band=WellbeingBand(current_band_value),
        )
    except (TypeError, ValueError):
        return None
