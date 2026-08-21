"""Preemptible runtime orchestration for autonomous pet activities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from project_akiha.core.behavior import ActivityState, CompanionMood
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.pet import PetState
from project_akiha.core.pet_activity import (
    AUTONOMOUS_ACTIVITY_SOURCE,
    PetActivityCancellationReason,
    PetActivityContext,
    PetActivityDefinition,
    PetActivityPriority,
    PetActivityScheduler,
    PetActivitySession,
)
from project_akiha.core.state.animation import AnimationState
from project_akiha.core.state.voice import VoiceState


class AutonomousActivityController:
    """Own autonomous animation requests below every direct interaction."""

    _direct_events = frozenset(
        {
            EventType.PET_WALK_REQUESTED,
            EventType.PET_IDLE_REQUESTED,
            EventType.PET_SLEEP_REQUESTED,
            EventType.PET_WAKE_REQUESTED,
            EventType.CHAT_OPEN_REQUESTED,
            EventType.SETTINGS_OPEN_REQUESTED,
        }
    )

    def __init__(
        self,
        event_bus: EventBus,
        definitions: tuple[PetActivityDefinition, ...],
        *,
        initial_user_activity: ActivityState,
        initial_mood: CompanionMood,
        initial_pet_state: PetState,
        initial_animation_state: AnimationState = AnimationState.IDLE,
        enabled: bool = True,
    ) -> None:
        self._event_bus = event_bus
        self._scheduler = PetActivityScheduler(definitions)
        self._user_activity = initial_user_activity
        self._mood = initial_mood
        self._pet_state = initial_pet_state
        self._animation_state = initial_animation_state
        self._voice_state = VoiceState.IDLE
        self._enabled = bool(enabled)
        self._active: PetActivitySession | None = None

        event_bus.subscribe(
            EventType.USER_ACTIVITY_STATE_CHANGED,
            self._handle_user_activity_changed,
        )
        event_bus.subscribe(EventType.MOOD_STATE_CHANGED, self._handle_mood_changed)
        event_bus.subscribe(EventType.STATE_CHANGED, self._handle_animation_changed)
        event_bus.subscribe(EventType.VOICE_STATE_CHANGED, self._handle_voice_changed)
        event_bus.subscribe(EventType.PET_DRAG_STARTED, self._handle_drag_started)
        event_bus.subscribe(
            EventType.PET_CARE_OPEN_REQUESTED,
            self._handle_care_interaction,
        )
        event_bus.subscribe(
            EventType.PET_CARE_COMPLETED,
            self._handle_care_interaction,
        )
        for event_type in self._direct_events:
            event_bus.subscribe(event_type, self._handle_direct_control)

    @property
    def active_session(self) -> PetActivitySession | None:
        """Return the current in-memory activity, if any."""
        return self._active

    def set_enabled(self, enabled: bool, now: datetime | None = None) -> None:
        """Enable scheduling or cancel autonomous behavior immediately."""
        self._enabled = bool(enabled)
        if not self._enabled:
            self._cancel(
                PetActivityCancellationReason.DISABLED,
                now or _now(),
                restore_idle=True,
            )

    def observe_pet_state(self, state: PetState, now: datetime | None = None) -> None:
        """Refresh typed pet context without parsing dialogue or events."""
        if not isinstance(state, PetState):
            raise TypeError("state must be a PetState value.")
        self._pet_state = state
        self._reconcile_context(now or _now())

    def tick(self, now: datetime | None = None) -> None:
        """Advance one bounded lifecycle and select at most one new activity."""
        current_time = now or _now()
        _require_aware(current_time)
        if not self._enabled or self._voice_busy:
            return
        if self._active is not None:
            if current_time < self._active.ends_at:
                return
            self._finish(current_time)
            return
        if self._animation_state is not AnimationState.IDLE:
            return

        decision = self._scheduler.select(self._context(current_time))
        if decision.definition is None:
            return
        self._start(decision.definition, current_time)

    def shutdown(self, now: datetime | None = None) -> None:
        """End autonomous state without affecting persisted pet data."""
        self._cancel(
            PetActivityCancellationReason.SHUTDOWN,
            now or _now(),
            restore_idle=False,
        )

    @property
    def _voice_busy(self) -> bool:
        return self._voice_state in {
            VoiceState.LISTENING,
            VoiceState.THINKING,
            VoiceState.SPEAKING,
        }

    def _start(self, definition: PetActivityDefinition, now: datetime) -> None:
        self._active = PetActivitySession(
            definition=definition,
            started_at=now,
            ends_at=now + timedelta(seconds=definition.duration_seconds),
        )
        self._event_bus.publish(
            EventType.PET_ACTIVITY_STARTED,
            {
                "kind": f"pet_activity_{definition.activity_id.value}_started",
                "activity_id": definition.activity_id.value,
                "animation_state": definition.animation_state.value,
                "duration_seconds": definition.duration_seconds,
                "source": AUTONOMOUS_ACTIVITY_SOURCE,
            },
        )
        self._request_animation(definition.animation_state)
        if self._animation_state is not definition.animation_state:
            self._cancel(
                PetActivityCancellationReason.TRANSITION_REJECTED,
                now,
                restore_idle=False,
            )

    def _finish(self, now: datetime) -> None:
        session = self._active
        if session is None:
            return
        self._active = None
        self._scheduler.mark_finished(session.definition.activity_id, now)
        self._event_bus.publish(
            EventType.PET_ACTIVITY_COMPLETED,
            {
                "kind": (
                    f"pet_activity_{session.definition.activity_id.value}_completed"
                ),
                "activity_id": session.definition.activity_id.value,
                "animation_state": session.definition.animation_state.value,
                "duration_seconds": session.definition.duration_seconds,
                "source": AUTONOMOUS_ACTIVITY_SOURCE,
            },
        )
        self._request_animation(AnimationState.IDLE)

    def _cancel(
        self,
        reason: PetActivityCancellationReason,
        now: datetime,
        *,
        restore_idle: bool,
    ) -> None:
        session = self._active
        if session is None:
            return
        self._active = None
        self._scheduler.mark_finished(session.definition.activity_id, now)
        elapsed = max(0, int((now - session.started_at).total_seconds()))
        self._event_bus.publish(
            EventType.PET_ACTIVITY_CANCELLED,
            {
                "kind": (
                    f"pet_activity_{session.definition.activity_id.value}_cancelled"
                ),
                "activity_id": session.definition.activity_id.value,
                "animation_state": session.definition.animation_state.value,
                "elapsed_seconds": elapsed,
                "reason": reason.value,
                "source": AUTONOMOUS_ACTIVITY_SOURCE,
            },
        )
        if restore_idle and self._animation_state is not AnimationState.IDLE:
            self._request_animation(AnimationState.IDLE)

    def _preempt(
        self,
        priority: PetActivityPriority,
        reason: PetActivityCancellationReason,
        now: datetime,
        *,
        restore_idle: bool,
    ) -> None:
        if priority <= PetActivityPriority.AUTONOMOUS:
            return
        self._cancel(reason, now, restore_idle=restore_idle)

    def _reconcile_context(self, now: datetime) -> None:
        if self._active is None:
            return
        if not self._scheduler.is_eligible(
            self._active.definition,
            self._context(now),
        ):
            self._preempt(
                PetActivityPriority.DIRECT_CONTROL,
                PetActivityCancellationReason.CONTEXT_CHANGED,
                now,
                restore_idle=True,
            )

    def _context(self, now: datetime) -> PetActivityContext:
        return PetActivityContext(
            now=now,
            user_activity=self._user_activity,
            mood=self._mood,
            pet_state=self._pet_state,
            animation_state=self._animation_state,
        )

    def _request_animation(self, state: AnimationState) -> None:
        event_type = {
            AnimationState.IDLE: EventType.PET_IDLE_REQUESTED,
            AnimationState.WALKING: EventType.PET_WALK_REQUESTED,
            AnimationState.SLEEPING: EventType.PET_SLEEP_REQUESTED,
        }.get(state)
        if event_type is None:
            raise ValueError("Autonomous activities cannot request this animation.")
        self._event_bus.publish(
            event_type,
            {
                "source": AUTONOMOUS_ACTIVITY_SOURCE,
                "activity_id": (
                    self._active.definition.activity_id.value
                    if self._active is not None
                    else None
                ),
            },
        )

    def _handle_user_activity_changed(self, event: Event) -> None:
        state_value = event.payload.get("state")
        if not isinstance(state_value, str):
            return
        try:
            self._user_activity = ActivityState(state_value)
        except ValueError:
            return
        self._reconcile_context(_now())

    def _handle_mood_changed(self, event: Event) -> None:
        mood_value = event.payload.get("mood")
        if not isinstance(mood_value, str):
            return
        try:
            self._mood = CompanionMood(mood_value)
        except ValueError:
            return
        self._reconcile_context(_now())

    def _handle_animation_changed(self, event: Event) -> None:
        state_value = event.payload.get("state")
        if not isinstance(state_value, str):
            return
        try:
            self._animation_state = AnimationState(state_value)
        except ValueError:
            return

    def _handle_voice_changed(self, event: Event) -> None:
        state_value = event.payload.get("state")
        if not isinstance(state_value, str):
            return
        try:
            self._voice_state = VoiceState(state_value)
        except ValueError:
            return
        if self._voice_busy:
            self._preempt(
                PetActivityPriority.VOICE,
                PetActivityCancellationReason.VOICE_ACTIVITY,
                _now(),
                restore_idle=True,
            )

    def _handle_drag_started(self, event: Event) -> None:
        del event
        self._preempt(
            PetActivityPriority.DRAG,
            PetActivityCancellationReason.DRAG_STARTED,
            _now(),
            restore_idle=False,
        )

    def _handle_care_interaction(self, event: Event) -> None:
        del event
        self._preempt(
            PetActivityPriority.CARE_REACTION,
            PetActivityCancellationReason.CARE_INTERACTION,
            _now(),
            restore_idle=True,
        )

    def _handle_direct_control(self, event: Event) -> None:
        if event.payload.get("source") == AUTONOMOUS_ACTIVITY_SOURCE:
            return
        self._preempt(
            PetActivityPriority.DIRECT_CONTROL,
            PetActivityCancellationReason.DIRECT_CONTROL,
            _now(),
            restore_idle=False,
        )


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("activity time must be timezone-aware.")
