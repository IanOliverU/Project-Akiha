"""Application-level orchestration for Phase 7 voice state."""

from __future__ import annotations

from enum import StrEnum

from project_akiha.config import VoiceConfig
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.core.state.voice import (
    InvalidVoiceTransitionError,
    VoiceState,
    VoiceStateMachine,
)


class _VoiceOperation(StrEnum):
    NONE = "none"
    INPUT = "input"
    OUTPUT = "output"


class VoiceController:
    """Translate voice requests into explicit runtime state events."""

    def __init__(
        self,
        event_bus: EventBus,
        config: VoiceConfig,
    ) -> None:
        self._event_bus = event_bus
        self._config = config
        initial_state = VoiceState.IDLE if config.enabled else VoiceState.MUTED
        self._state_machine = VoiceStateMachine(initial_state)
        self._operation = _VoiceOperation.NONE

        event_bus.subscribe(
            EventType.VOICE_LISTEN_REQUESTED,
            self._handle_listen_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_STOP_REQUESTED,
            self._handle_listen_stop_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_LISTEN_CANCEL_REQUESTED,
            self._handle_listen_cancel_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_SPEAK_REQUESTED,
            self._handle_speak_requested,
        )
        event_bus.subscribe(
            EventType.VOICE_SPEAK_STOP_REQUESTED,
            self._handle_speak_stop_requested,
        )

        startup_reason = "startup" if config.enabled else "startup_disabled"
        self._publish_state(initial_state, initial_state, startup_reason)

    @property
    def state(self) -> VoiceState:
        """Return the current runtime voice state."""
        return self._state_machine.state

    @property
    def config(self) -> VoiceConfig:
        """Return the active voice configuration."""
        return self._config

    def apply_config(self, config: VoiceConfig) -> None:
        """Apply voice settings without requiring an app restart."""
        self._config = config
        if not config.enabled:
            if self._transition_to(VoiceState.MUTED, "voice_disabled"):
                self._operation = _VoiceOperation.NONE
        elif self.state == VoiceState.MUTED:
            self._transition_to(VoiceState.IDLE, "voice_enabled")
        elif self._operation == _VoiceOperation.INPUT and not config.input_enabled:
            if self._transition_to(VoiceState.IDLE, "input_disabled"):
                self._operation = _VoiceOperation.NONE
        elif self._operation == _VoiceOperation.OUTPUT and not config.output_enabled:
            if self._transition_to(VoiceState.IDLE, "output_disabled"):
                self._operation = _VoiceOperation.NONE

    def mark_speaking(self) -> None:
        """Mark that synthesized audio playback has started."""
        if not self._ensure_output_enabled():
            return
        if self._operation != _VoiceOperation.OUTPUT:
            self._publish_error(
                code="unexpected_playback",
                message="Speech playback started without an active request.",
            )
            return
        self._transition_to(VoiceState.SPEAKING, "playback_started")

    def publish_transcript(
        self,
        text: str,
        detected_language: str | None = None,
    ) -> None:
        """Publish an accepted transcript without sending it to chat."""
        if self._operation != _VoiceOperation.INPUT:
            self._publish_error(
                code="unexpected_transcript",
                message="A transcript arrived without an active input request.",
            )
            return
        if not self._config.input_enabled:
            self._publish_error(
                code="transcript_discarded",
                message="A transcript arrived after speech input was disabled.",
            )
            self._operation = _VoiceOperation.NONE
            return

        cleaned_text = text.strip()
        if not cleaned_text:
            self._publish_error(
                code="empty_transcript",
                message="Speech recognition returned an empty transcript.",
            )
            if self._transition_to(VoiceState.IDLE, "empty_transcript"):
                self._operation = _VoiceOperation.NONE
            return

        if not self._transition_to(VoiceState.IDLE, "transcription_complete"):
            return
        self._operation = _VoiceOperation.NONE
        payload: dict[str, object] = {"text": cleaned_text}
        if detected_language:
            payload["detected_language"] = detected_language
        self._event_bus.publish(EventType.VOICE_TRANSCRIPT_READY, payload)

    def report_error(self, code: str, message: str) -> None:
        """Move to the error state and publish a privacy-safe diagnostic."""
        if self._transition_to(VoiceState.ERROR, "voice_error"):
            self._operation = _VoiceOperation.NONE
        self._publish_error(code=code, message=message)

    def recover(self) -> None:
        """Recover from a completed or failed voice operation."""
        target = VoiceState.IDLE if self._config.enabled else VoiceState.MUTED
        if self._transition_to(target, "recovered"):
            self._operation = _VoiceOperation.NONE

    def _handle_listen_requested(self, event: Event) -> None:
        del event
        if not self._ensure_input_enabled():
            return
        if not self._config.push_to_talk_enabled:
            self._publish_error(
                code="push_to_talk_disabled",
                message="Push-to-talk is disabled.",
            )
            return
        if self._transition_to(VoiceState.LISTENING, "listen_requested"):
            self._operation = _VoiceOperation.INPUT

    def _handle_listen_stop_requested(self, event: Event) -> None:
        del event
        if (
            self._operation == _VoiceOperation.INPUT
            and self.state == VoiceState.LISTENING
        ):
            self._transition_to(VoiceState.THINKING, "transcription_started")

    def _handle_listen_cancel_requested(self, event: Event) -> None:
        del event
        if self._operation == _VoiceOperation.INPUT and self.state in {
            VoiceState.LISTENING,
            VoiceState.THINKING,
        }:
            if self._transition_to(VoiceState.IDLE, "listening_cancelled"):
                self._operation = _VoiceOperation.NONE

    def _handle_speak_requested(self, event: Event) -> None:
        if not self._ensure_output_enabled():
            return

        text = event.payload.get("text")
        if not isinstance(text, str) or not text.strip():
            self._publish_error(
                code="invalid_speech_request",
                message="Speech output requires non-empty text.",
            )
            return
        if self._transition_to(VoiceState.THINKING, "synthesis_started"):
            self._operation = _VoiceOperation.OUTPUT

    def _handle_speak_stop_requested(self, event: Event) -> None:
        del event
        if self._operation == _VoiceOperation.OUTPUT and self.state in {
            VoiceState.THINKING,
            VoiceState.SPEAKING,
        }:
            if self._transition_to(VoiceState.IDLE, "speech_stopped"):
                self._operation = _VoiceOperation.NONE

    def _ensure_input_enabled(self) -> bool:
        if not self._config.enabled:
            self._publish_error("voice_disabled", "Voice is disabled.")
            return False
        if not self._config.input_enabled:
            self._publish_error("input_disabled", "Speech input is disabled.")
            return False
        return True

    def _ensure_output_enabled(self) -> bool:
        if not self._config.enabled:
            self._publish_error("voice_disabled", "Voice is disabled.")
            return False
        if not self._config.output_enabled:
            self._publish_error("output_disabled", "Speech output is disabled.")
            return False
        return True

    def _transition_to(self, next_state: VoiceState, reason: str) -> bool:
        previous_state = self._state_machine.state
        try:
            current_state = self._state_machine.transition_to(next_state)
        except InvalidVoiceTransitionError as error:
            self._publish_error(
                code="invalid_transition",
                message=str(error),
            )
            return False

        if current_state != previous_state:
            self._publish_state(previous_state, current_state, reason)
        return True

    def _publish_state(
        self,
        previous_state: VoiceState,
        current_state: VoiceState,
        reason: str,
    ) -> None:
        self._event_bus.publish(
            EventType.VOICE_STATE_CHANGED,
            {
                "state": current_state.value,
                "previous_state": previous_state.value,
                "reason": reason,
            },
        )

    def _publish_error(self, code: str, message: str) -> None:
        self._event_bus.publish(
            EventType.VOICE_ERROR_OCCURRED,
            {
                "source": "voice_controller",
                "code": code.strip() or "voice_error",
                "message": message.strip() or "Unknown voice error.",
                "state": self.state.value,
            },
        )
