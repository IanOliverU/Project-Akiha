"""Policy-gated ingress for validated external communication events."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from project_akiha.config import ExternalIntegrationsConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    NotificationPolicy,
    NotificationRequest,
    NotificationUrgency,
)
from project_akiha.core.events import Event, EventBus, EventType
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
        preference_provider: Callable[[], ExternalIntegrationsConfig] | None = None,
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
        self._preference_provider = preference_provider or ExternalIntegrationsConfig
        self._last_notification_at: datetime | None = None
        self._last_receipt_prune_at: datetime | None = None
        self._pending_receipts: dict[str, deque[ExternalEvent]] = defaultdict(deque)
        event_bus.subscribe(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            self._handle_delivery_result,
        )

    def submit(self, candidate: ExternalEvent) -> str:
        """Accept one provider candidate without publishing it directly."""
        try:
            event = self._validator.validate(candidate)
        except ExternalEventValidationError:
            self._logger.warning("External event rejected: invalid_payload")
            return "invalid"

        received_at = self._now_provider()
        try:
            self._prune_receipts_if_due(received_at)
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

    def _prune_receipts_if_due(self, now: datetime) -> None:
        if (
            self._last_receipt_prune_at is not None
            and now - self._last_receipt_prune_at < timedelta(days=1)
        ):
            return
        retention_days = self._preference_provider().receipt_retention_days
        self._repository.prune_receipts(older_than=now - timedelta(days=retention_days))
        self._last_receipt_prune_at = now

    def _process_on_app_thread(self, event: ExternalEvent) -> None:
        now = self._now_provider()
        self._event_bus.publish(
            EventType.EXTERNAL_EVENT_ACCEPTED,
            _privacy_safe_event_payload(event),
        )
        if event.priority == ExternalEventPriority.SILENT:
            self._safe_set_status(event, ExternalNotificationStatus.SILENT)
            return

        preferences = self._preference_provider()
        age_seconds = max(0.0, (now - event.occurred_at).total_seconds())
        if age_seconds > preferences.event_expiry_seconds:
            self._safe_set_status(event, ExternalNotificationStatus.EXPIRED)
            return
        if not _event_notification_enabled(event, preferences):
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return
        if not (
            preferences.visual_notifications_enabled
            or preferences.voice_notifications_enabled
        ):
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
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

        self._last_notification_at = now
        self._safe_set_status(event, ExternalNotificationStatus.QUEUED)
        self._pending_receipts[request.kind].append(event)
        payload = {
            "kind": request.kind,
            "message": request.message,
            "urgency": request.urgency.value,
            "created_at": now.isoformat(),
            "source": "external_integration",
        }
        if preferences.visual_notifications_enabled:
            self._event_bus.publish(EventType.PROACTIVE_SUGGESTION_READY, payload)
        elif preferences.voice_notifications_enabled:
            self._event_bus.publish(
                EventType.PROACTIVE_SUGGESTION_DELIVERED,
                {
                    **payload,
                    "delivered": True,
                    "channel": "voice_only",
                    "reason": "visual_notifications_disabled",
                },
            )

    def publish_health(
        self,
        service: str,
        status: str,
        checked_at: datetime,
    ) -> None:
        """Schedule one allowlisted privacy-safe provider health event."""
        allowed_services = {"gmail", "discord"}
        if service not in allowed_services or not _valid_health_code(status):
            self._logger.warning("External health update rejected: invalid_status")
            return
        self._schedule_on_app_thread(
            lambda: self._event_bus.publish(
                EventType.EXTERNAL_INTEGRATION_HEALTH_CHANGED,
                {
                    "service": service,
                    "status": status,
                    "checked_at": checked_at.isoformat(),
                },
            )
        )

    def _handle_delivery_result(self, event: Event) -> None:
        payload = event.payload
        kind = payload.get("kind")
        if not isinstance(kind, str) or not kind.startswith("external."):
            return
        pending = self._pending_receipts.get(kind)
        if not pending:
            return
        external_event = pending.popleft()
        if not pending:
            self._pending_receipts.pop(kind, None)
        delivered = payload.get("delivered") is True
        self._safe_set_status(
            external_event,
            (
                ExternalNotificationStatus.DELIVERED
                if delivered
                else ExternalNotificationStatus.SUPPRESSED
            ),
            notified_at=self._now_provider() if delivered else None,
        )

    def _safe_set_status(
        self,
        event: ExternalEvent,
        status: ExternalNotificationStatus,
        *,
        notified_at: datetime | None = None,
    ) -> None:
        try:
            self._repository.set_notification_status(
                event,
                status,
                notified_at=notified_at,
            )
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


def _event_notification_enabled(
    event: ExternalEvent,
    config: ExternalIntegrationsConfig,
) -> bool:
    if event.service.value == "gmail":
        gmail = config.gmail
        return {
            "interview": gmail.notify_interview,
            "recruiter": gmail.notify_recruiter,
            "important": gmail.notify_important,
            "work": gmail.notify_work,
            "personal": gmail.notify_personal,
            "newsletter": gmail.notify_newsletter,
            "promotional": gmail.notify_promotional,
        }.get(event.classification.value, gmail.notify_new_messages)
    discord = config.discord
    return {
        "discord.bot_direct_message": discord.notify_bot_direct_messages,
        "discord.mention": discord.notify_mentions,
        "discord.authorized_channel_message": (discord.notify_authorized_channels),
    }.get(event.kind.value, False)


def _valid_health_code(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 64
        and all(
            character.islower() or character.isdecimal() or character == "_"
            for character in value
        )
    )
