"""Policy-gated ingress for validated external communication events."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from project_akiha.core.behavior import (
    ActivitySnapshot,
    NotificationPolicy,
    NotificationRequest,
    NotificationUrgency,
)
from project_akiha.core.events import EventBus, EventType
from project_akiha.core.integrations import (
    ExternalEvent,
    ExternalEventPriority,
    ExternalEventRepository,
    ExternalNotificationStatus,
)
from project_akiha.services.external_event_validation import (
    ExternalEventValidationError,
    ExternalEventValidator,
)
from project_akiha.services.external_notification_renderer import (
    ExternalNotificationRenderer,
)

AppThreadScheduler = Callable[[Callable[[], None]], None]

_URGENCY_BY_PRIORITY = {
    ExternalEventPriority.CRITICAL: NotificationUrgency.HIGH,
    ExternalEventPriority.IMPORTANT: NotificationUrgency.HIGH,
    ExternalEventPriority.NORMAL: NotificationUrgency.NORMAL,
    ExternalEventPriority.LOW: NotificationUrgency.LOW,
}


class IntegrationNotificationCoordinator:
    """Validate, deduplicate, schedule, and policy-gate external notices."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        validator: ExternalEventValidator,
        repository: ExternalEventRepository,
        notification_policy: NotificationPolicy,
        renderer: ExternalNotificationRenderer,
        activity_provider: Callable[[], ActivitySnapshot],
        schedule_on_app_thread: AppThreadScheduler,
        now_provider: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._validator = validator
        self._repository = repository
        self._notification_policy = notification_policy
        self._renderer = renderer
        self._activity_provider = activity_provider
        self._schedule_on_app_thread = schedule_on_app_thread
        self._now_provider = now_provider or (lambda: datetime.now(tz=UTC))
        self._logger = logger or logging.getLogger("project_akiha.integrations")
        self._last_notification_at: datetime | None = None

    def submit(self, candidate: ExternalEvent) -> str:
        """Accept one provider candidate without publishing it directly."""
        try:
            event = self._validator.validate(candidate)
        except ExternalEventValidationError:
            self._logger.warning("External event rejected: invalid_payload")
            return "invalid"

        received_at = self._now_provider()
        try:
            if not self._repository.claim_event(event, received_at=received_at):
                return "duplicate"
        except Exception:
            self._logger.exception("External event rejected: dedupe_unavailable")
            return "repository_error"

        try:
            self._schedule_on_app_thread(lambda: self._process_on_app_thread(event))
        except Exception:
            self._logger.exception("External event rejected: scheduling_failed")
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return "scheduling_error"
        return "scheduled"

    def _process_on_app_thread(self, event: ExternalEvent) -> None:
        now = self._now_provider()
        self._event_bus.publish(
            EventType.EXTERNAL_EVENT_ACCEPTED,
            _privacy_safe_event_payload(event),
        )
        if event.priority == ExternalEventPriority.SILENT:
            self._safe_set_status(event, ExternalNotificationStatus.SILENT)
            return

        try:
            message = self._renderer.render(event)
            urgency = _URGENCY_BY_PRIORITY[event.priority]
            request = NotificationRequest(
                kind=_notification_kind(event),
                message=message,
                urgency=urgency,
            )
            decision = self._notification_policy.evaluate(
                request,
                activity=self._activity_provider(),
                now=now,
                last_notification_at=self._last_notification_at,
            )
        except Exception:
            self._logger.exception("External notification preparation failed.")
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return

        if not decision.allowed:
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return

        self._event_bus.publish(
            EventType.PROACTIVE_SUGGESTION_READY,
            {
                "kind": request.kind,
                "message": request.message,
                "urgency": request.urgency.value,
                "created_at": now.isoformat(),
                "source": "external_integration",
            },
        )
        self._last_notification_at = now
        self._safe_set_status(event, ExternalNotificationStatus.QUEUED)

    def _safe_set_status(
        self,
        event: ExternalEvent,
        status: ExternalNotificationStatus,
    ) -> None:
        try:
            self._repository.set_notification_status(event, status)
        except Exception:
            self._logger.exception(
                "External receipt status update failed: %s",
                status.value,
            )


def _notification_kind(event: ExternalEvent) -> str:
    return f"external.{event.kind.value}"


def _privacy_safe_event_payload(event: ExternalEvent) -> dict[str, object]:
    return {
        "service": event.service.value,
        "kind": event.kind.value,
        "classification": event.classification.value,
        "priority": event.priority.value,
        "sender_present": event.sender_display is not None,
        "subject_present": event.subject is not None,
        "context_present": event.context_label is not None,
        "occurred_at": event.occurred_at.isoformat(),
    }
