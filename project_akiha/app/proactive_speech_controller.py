"""Speak proactive suggestions only after successful policy-gated delivery."""

from __future__ import annotations

from collections.abc import Callable

from project_akiha.app.assistant_speech_controller import AssistantSpeechController
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType
from project_akiha.services.speech_identity import proactive_speech_line


class ProactiveSpeechController:
    """Route delivered proactive events into the opt-in speech policy."""

    def __init__(
        self,
        event_bus: EventBus,
        speech_controller: AssistantSpeechController,
        *,
        line_provider: Callable[[str], str | None] = proactive_speech_line,
    ) -> None:
        self._speech_controller = speech_controller
        self._line_provider = line_provider
        event_bus.subscribe(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            self._handle_suggestion_delivered,
        )

    def _handle_suggestion_delivered(self, event: Event) -> None:
        if event.payload.get("delivered") is not True:
            return

        kind = event.payload.get("kind")
        if not isinstance(kind, str):
            return

        message = event.payload.get("message")
        line = (
            message
            if kind.startswith("external.") and isinstance(message, str)
            else self._line_provider(kind)
        )
        if line is not None:
            self._speech_controller.submit_proactive_suggestion(line)
