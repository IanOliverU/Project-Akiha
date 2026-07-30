"""Log high-level application events from the EventBus."""

from __future__ import annotations

import logging

from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class EventLogger:
    """Subscribe to app events and write useful diagnostics."""

    def __init__(
        self,
        event_bus: EventBus,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger("project_akiha.events")
        for event_type in EventType:
            event_bus.subscribe(event_type, self._handle_event)

    def _handle_event(self, event: Event) -> None:
        payload = _privacy_safe_payload(event)
        if event.event_type in {
            EventType.ERROR_OCCURRED,
            EventType.VOICE_ERROR_OCCURRED,
        }:
            self._logger.error("%s %s", event.event_type.value, payload)
        elif event.event_type == EventType.PET_DRAGGED:
            self._logger.debug("%s %s", event.event_type.value, payload)
        else:
            self._logger.info("%s %s", event.event_type.value, payload)


def _privacy_safe_payload(event: Event) -> dict[str, object]:
    if event.event_type == EventType.VOICE_SPEAK_REQUESTED:
        text = event.payload.get("text")
        payload: dict[str, object] = {
            "text_present": isinstance(text, str) and bool(text.strip())
        }
        source = event.payload.get("source")
        if isinstance(source, str) and source:
            payload["source"] = source
        return payload
    if event.event_type in {
        EventType.VOICE_TRANSCRIPT_PARTIAL,
        EventType.VOICE_TRANSCRIPT_READY,
    }:
        text = event.payload.get("text")
        payload = {"text_present": isinstance(text, str) and bool(text.strip())}
        language = event.payload.get("detected_language")
        if isinstance(language, str) and language:
            payload["detected_language"] = language
        return payload
    return event.payload
