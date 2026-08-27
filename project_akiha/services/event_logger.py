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
        elif event.event_type in {
            EventType.PET_DRAGGED,
            EventType.VOICE_MICROPHONE_ACTIVITY_UPDATED,
        }:
            self._logger.debug("%s %s", event.event_type.value, payload)
        else:
            self._logger.info("%s %s", event.event_type.value, payload)


def _privacy_safe_payload(event: Event) -> dict[str, object]:
    if event.event_type == EventType.EXTERNAL_EVENT_ACCEPTED:
        return _external_event_audit_payload(event.payload)
    if event.event_type == EventType.EXTERNAL_INTEGRATION_HEALTH_CHANGED:
        return {
            key: event.payload[key]
            for key in ("service", "status", "checked_at")
            if key in event.payload
        }
    if event.event_type in {
        EventType.PROACTIVE_SUGGESTION_READY,
        EventType.PROACTIVE_SUGGESTION_DELIVERED,
    } and _is_external_notification(event.payload):
        payload = {
            key: event.payload[key]
            for key in (
                "kind",
                "urgency",
                "created_at",
                "source",
                "delivered",
                "channel",
                "reason",
            )
            if key in event.payload
        }
        message = event.payload.get("message")
        payload["message_present"] = isinstance(message, str) and bool(message.strip())
        return payload
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
        confidence_level = event.payload.get("confidence_level")
        if confidence_level in {"low", "medium", "high"}:
            payload["confidence_level"] = confidence_level
        if event.payload.get("requires_review") is True:
            payload["requires_review"] = True
        return payload
    return event.payload


def _is_external_notification(payload: dict[str, object]) -> bool:
    kind = payload.get("kind")
    return isinstance(kind, str) and kind.startswith("external.")


def _external_event_audit_payload(payload: dict[str, object]) -> dict[str, object]:
    allowed = {
        "service",
        "kind",
        "classification",
        "priority",
        "sender_present",
        "subject_present",
        "context_present",
        "occurred_at",
    }
    return {key: payload[key] for key in allowed if key in payload}
