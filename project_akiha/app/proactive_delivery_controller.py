"""Application-level delivery for proactive companion suggestions."""

from __future__ import annotations

from datetime import datetime

from project_akiha.core.behavior import (
    NotificationUrgency,
    ProactiveDeliveryRequest,
    ProactiveDeliveryResult,
    ProactiveDeliveryService,
    ProactiveDeliverySurface,
)
from project_akiha.core.events.bus import Event, EventBus
from project_akiha.core.events.types import EventType


class ProactiveDeliveryController:
    """Deliver allowed proactive suggestions to the current UI surface."""

    def __init__(
        self,
        event_bus: EventBus,
        delivery_service: ProactiveDeliveryService,
        surface: ProactiveDeliverySurface,
    ) -> None:
        self._event_bus = event_bus
        self._delivery_service = delivery_service
        self._surface = surface
        event_bus.subscribe(
            EventType.PROACTIVE_SUGGESTION_READY,
            self._handle_suggestion_ready,
        )

    def deliver_request(
        self,
        request: ProactiveDeliveryRequest,
    ) -> ProactiveDeliveryResult:
        """Deliver a request and publish the delivery result."""
        result = self._delivery_service.deliver(request, self._surface)
        self._publish_result(result)
        return result

    def _handle_suggestion_ready(self, event: Event) -> None:
        request = _request_from_payload(event.payload)
        if request is None:
            return
        result = self._delivery_service.deliver(request, self._surface)
        self._publish_result(result, source_payload=event.payload)

    def _publish_result(
        self,
        result: ProactiveDeliveryResult,
        *,
        source_payload: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "kind": result.request.kind,
            "message": result.request.message,
            "urgency": result.request.urgency.value,
            "created_at": result.request.created_at.isoformat(),
            "delivered": result.delivered,
            "channel": result.channel.value,
            "reason": result.reason,
        }
        if source_payload is not None:
            speech_message = source_payload.get("speech_message")
            if isinstance(speech_message, str) and speech_message.strip():
                payload["speech_message"] = speech_message
            if source_payload.get("speech_enabled") is False:
                payload["speech_enabled"] = False
            payload["aggregate_count"] = source_payload.get("aggregate_count", 1)
        self._event_bus.publish(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            payload,
        )


def _request_from_payload(
    payload: dict[str, object],
) -> ProactiveDeliveryRequest | None:
    kind = payload.get("kind")
    message = payload.get("message")
    urgency = payload.get("urgency")
    created_at = payload.get("created_at")

    if not isinstance(kind, str):
        return None
    if not isinstance(message, str):
        return None
    if not isinstance(urgency, str):
        return None
    if not isinstance(created_at, str):
        return None

    try:
        parsed_urgency = NotificationUrgency(urgency)
        parsed_created_at = datetime.fromisoformat(created_at)
    except ValueError:
        return None

    allow_chat = payload.get("chat_enabled", True)
    allow_tray = payload.get("visual_enabled", True)
    if not isinstance(allow_chat, bool) or not isinstance(allow_tray, bool):
        return None

    return ProactiveDeliveryRequest(
        kind=kind,
        message=message,
        urgency=parsed_urgency,
        created_at=parsed_created_at,
        allow_chat=allow_chat,
        allow_tray=allow_tray,
    )
