"""Coordinate push-to-talk takeover from active assistant output."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from project_akiha.app.voice_controller import VoiceController
from project_akiha.core.events.bus import EventBus
from project_akiha.core.events.types import EventType

_INTERRUPTION_SOURCE = "talk_interrupt"


@dataclass(frozen=True, slots=True)
class TalkInterruptionResult:
    """Describe which bounded work a Talk request interrupted."""

    output_stopped: bool
    work_cancelled: bool
    listening_requested: bool


class TalkInterruptionController:
    """Stop unfinished output before handing microphone ownership to Talk."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        voice_controller: VoiceController,
        has_interruptible_work: Callable[[], bool],
        cancel_interruptible_work: Callable[[], None],
    ) -> None:
        self._event_bus = event_bus
        self._voice_controller = voice_controller
        self._has_interruptible_work = has_interruptible_work
        self._cancel_interruptible_work = cancel_interruptible_work

    def request_talk(self) -> TalkInterruptionResult:
        """Interrupt active output and generation, then request microphone input."""
        config = self._voice_controller.config
        if not config.input_enabled or not config.push_to_talk_enabled:
            self._event_bus.publish(
                EventType.VOICE_LISTEN_REQUESTED,
                {"source": _INTERRUPTION_SOURCE},
            )
            return TalkInterruptionResult(
                output_stopped=False,
                work_cancelled=False,
                listening_requested=False,
            )

        output_active = self._voice_controller.operation == "output"
        work_active = self._has_interruptible_work()
        if output_active:
            self._event_bus.publish(
                EventType.VOICE_SPEAK_STOP_REQUESTED,
                {"reason": _INTERRUPTION_SOURCE},
            )
        if work_active:
            self._cancel_interruptible_work()

        self._event_bus.publish(
            EventType.VOICE_LISTEN_REQUESTED,
            {"source": _INTERRUPTION_SOURCE},
        )
        return TalkInterruptionResult(
            output_stopped=output_active,
            work_cancelled=work_active,
            listening_requested=True,
        )
