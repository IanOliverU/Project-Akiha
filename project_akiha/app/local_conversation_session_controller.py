"""Own the explicit lifecycle of a local multi-turn voice session."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import (
    VoiceSessionCoordinator,
    VoiceSessionSnapshot,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import VoiceState
from project_akiha.core.voice_session import SessionLifecycle, VoiceProcessingMode

_SESSION_SOURCE = "local_conversation"


class LocalConversationSessionController:
    """Start and end one user-authorized local conversation session."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        voice_controller: VoiceController,
        session_coordinator: VoiceSessionCoordinator,
        processing_mode_provider: Callable[[], VoiceProcessingMode],
        has_interruptible_work: Callable[[], bool],
        cancel_interruptible_work: Callable[[], None],
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._coordinator = session_coordinator
        self._processing_mode_provider = processing_mode_provider
        self._has_interruptible_work = has_interruptible_work
        self._cancel_interruptible_work = cancel_interruptible_work
        self._monotonic_clock = monotonic_clock
        self._active = False
        self._started_at: float | None = None
        self._last_user_activity_at: float | None = None
        session_coordinator.subscribe(self._handle_session_snapshot)
        event_bus.subscribe(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            self._handle_response_playback_completed,
        )
        event_bus.subscribe(
            EventType.VOICE_TRANSCRIPT_READY,
            self._handle_transcript_ready,
        )

    @property
    def active(self) -> bool:
        """Return whether the user explicitly started conversation mode."""
        return self._active

    def start(self) -> bool:
        """Start a persistent session and open its first microphone turn."""
        config = self._voice_controller.config
        if self._active:
            return False
        if not config.input_enabled or not config.push_to_talk_enabled:
            self._voice_controller.notify_error(
                "conversation_input_unavailable",
                "Local conversation requires enabled push-to-talk input.",
            )
            return False
        if (
            self._voice_controller.state is not VoiceState.IDLE
            or self._voice_controller.operation != "none"
            or self._coordinator.snapshot.lifecycle is not SessionLifecycle.IDLE
            or self._has_interruptible_work()
        ):
            self._voice_controller.notify_error(
                "conversation_session_busy",
                "Finish the current voice operation before starting conversation.",
            )
            return False

        try:
            self._coordinator.request_start(self._processing_mode_provider())
            self._coordinator.activate()
        except (RuntimeError, TypeError, ValueError) as error:
            self._coordinator.close()
            self._voice_controller.notify_error(
                "conversation_session_start_failed",
                f"Local conversation could not start: {error}",
            )
            return False

        now = self._monotonic_clock()
        self._started_at = now
        self._last_user_activity_at = now
        self._set_active(True)
        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": _SESSION_SOURCE},
        )
        return True

    def end(self, reason: str = "user") -> bool:
        """Cancel unfinished work and release the persistent session."""
        if not self._active:
            return False

        self._set_active(False, reason=reason)
        if self._voice_controller.operation == "input":
            self._event_bus.publish(
                EventType.VOICE_LISTEN_CANCEL_REQUESTED,
                {"reason": "conversation_ended"},
            )
        elif self._voice_controller.operation == "output":
            self._event_bus.publish(
                EventType.VOICE_SPEAK_STOP_REQUESTED,
                {"reason": "conversation_ended"},
            )
        self._cancel_interruptible_work()
        self._coordinator.close()
        return True

    def tick(self) -> None:
        """Publish elapsed state and stop a session at either local limit."""
        if not self._active:
            return
        now = self._monotonic_clock()
        elapsed_seconds, idle_seconds = self._elapsed_times(now)
        config = self._voice_controller.config
        if elapsed_seconds >= config.local_conversation_max_duration_seconds:
            self.end("session_timeout")
            return
        if (
            idle_seconds >= config.local_conversation_idle_timeout_seconds
            and not self._idle_timeout_deferred()
        ):
            self.end("idle_timeout")
            return
        self._publish_state(
            active=True,
            elapsed_seconds=elapsed_seconds,
            idle_seconds=idle_seconds,
        )

    def close(self) -> None:
        """Release coordinator observation and active resources on shutdown."""
        if self._active:
            self.end()
        self._coordinator.unsubscribe(self._handle_session_snapshot)
        self._event_bus.unsubscribe(
            EventType.VOICE_RESPONSE_PLAYBACK_COMPLETED,
            self._handle_response_playback_completed,
        )
        self._event_bus.unsubscribe(
            EventType.VOICE_TRANSCRIPT_READY,
            self._handle_transcript_ready,
        )

    def _handle_session_snapshot(self, snapshot: VoiceSessionSnapshot) -> None:
        if self._active and snapshot.lifecycle in {
            SessionLifecycle.IDLE,
            SessionLifecycle.ERROR,
        }:
            reason = (
                "session_error"
                if snapshot.lifecycle is SessionLifecycle.ERROR
                else "session_closed"
            )
            self.end(reason)

    def _handle_transcript_ready(self, event: Event) -> None:
        text = event.payload.get("text")
        if self._active and isinstance(text, str) and text.strip():
            self._last_user_activity_at = self._monotonic_clock()

    def _handle_response_playback_completed(self, event: Event) -> None:
        if event.payload.get("source") != "assistant_reply" or not self._active:
            return
        snapshot = self._coordinator.snapshot
        if (
            snapshot.lifecycle is not SessionLifecycle.ACTIVE
            or snapshot.active_turn is not None
            or self._voice_controller.state is not VoiceState.IDLE
            or self._voice_controller.operation != "none"
            or self._has_interruptible_work()
        ):
            return
        config = self._voice_controller.config
        if not config.input_enabled or not config.push_to_talk_enabled:
            self.end()
            return
        self._last_user_activity_at = self._monotonic_clock()
        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": "local_conversation_resume"},
        )

    def _idle_timeout_deferred(self) -> bool:
        if self._has_interruptible_work():
            return True
        if self._voice_controller.operation == "output":
            return True
        return (
            self._voice_controller.operation == "input"
            and self._voice_controller.state is VoiceState.THINKING
        )

    def _set_active(self, active: bool, *, reason: str = "") -> None:
        if self._active == active:
            return
        self._active = active
        elapsed_seconds, idle_seconds = self._elapsed_times(self._monotonic_clock())
        self._publish_state(
            active=active,
            elapsed_seconds=elapsed_seconds,
            idle_seconds=idle_seconds,
            reason=reason,
        )
        if not active:
            self._started_at = None
            self._last_user_activity_at = None

    def _elapsed_times(self, now: float) -> tuple[int, int]:
        started_at = self._started_at
        last_activity_at = self._last_user_activity_at
        if started_at is None or last_activity_at is None:
            return 0, 0
        return (
            max(0, int(now - started_at)),
            max(0, int(now - last_activity_at)),
        )

    def _publish_state(
        self,
        *,
        active: bool,
        elapsed_seconds: int,
        idle_seconds: int,
        reason: str = "",
    ) -> None:
        self._event_bus.publish(
            EventType.VOICE_CONVERSATION_STATE_CHANGED,
            {
                "active": active,
                "mode": "local",
                "elapsed_seconds": elapsed_seconds,
                "idle_seconds": idle_seconds,
                "reason": reason,
            },
        )
