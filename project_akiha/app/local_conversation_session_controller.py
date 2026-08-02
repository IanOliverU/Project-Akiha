"""Own the explicit lifecycle of a local multi-turn voice session."""

from __future__ import annotations

from collections.abc import Callable

from project_akiha.app.voice_controller import VoiceController
from project_akiha.app.voice_session_coordinator import (
    VoiceSessionCoordinator,
    VoiceSessionSnapshot,
)
from project_akiha.core.events.bus import EventBus
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
        cancel_interruptible_work: Callable[[], None],
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._coordinator = session_coordinator
        self._processing_mode_provider = processing_mode_provider
        self._cancel_interruptible_work = cancel_interruptible_work
        self._active = False
        session_coordinator.subscribe(self._handle_session_snapshot)

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

        self._set_active(True)
        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": _SESSION_SOURCE},
        )
        return True

    def end(self) -> bool:
        """Cancel unfinished work and release the persistent session."""
        if not self._active:
            return False

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
        self._set_active(False)
        return True

    def close(self) -> None:
        """Release coordinator observation and active resources on shutdown."""
        if self._active:
            self.end()
        self._coordinator.unsubscribe(self._handle_session_snapshot)

    def _handle_session_snapshot(self, snapshot: VoiceSessionSnapshot) -> None:
        if self._active and snapshot.lifecycle in {
            SessionLifecycle.IDLE,
            SessionLifecycle.ERROR,
        }:
            self._set_active(False)

    def _set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._event_bus.publish(
            EventType.VOICE_CONVERSATION_STATE_CHANGED,
            {
                "active": active,
                "mode": "local",
            },
        )
