"""Policy-gated ingress for validated external communication events."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
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
from project_akiha.core.notifications import (
    NotificationInboxRepository,
    NotificationInboxStatus,
    PendingNotificationBatch,
    PendingNotificationQueue,
    SanitizedNotification,
)
from project_akiha.core.notifications.pending import PendingNotification
from project_akiha.services.external_event_validation import (
    ExternalEventValidationError,
    ExternalEventValidator,
)
from project_akiha.services.external_notification_channel_policy import (
    ExternalNotificationChannelPolicy,
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
_MAXIMUM_NOTIFICATION_RECORDS = 500


@dataclass(frozen=True, slots=True)
class _ReceiptLink:
    event: ExternalEvent
    inbox_record_id: int | None


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
        inbox_repository: NotificationInboxRepository | None = None,
        channel_policy: ExternalNotificationChannelPolicy | None = None,
        presentation_busy_provider: Callable[[], bool] | None = None,
        pending_queue: PendingNotificationQueue | None = None,
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
        self._inbox_repository = inbox_repository
        self._channel_policy = channel_policy or ExternalNotificationChannelPolicy()
        self._presentation_busy_provider = presentation_busy_provider or (lambda: False)
        self._pending_queue = pending_queue or PendingNotificationQueue()
        self._last_notification_at_by_kind: dict[str, datetime] = {}
        self._last_receipt_prune_at: datetime | None = None
        self._pending_receipts: dict[str, deque[_ReceiptLink]] = defaultdict(deque)
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
        preferences = self._preference_provider()
        age_seconds = max(0.0, (now - event.occurred_at).total_seconds())
        if age_seconds > preferences.event_expiry_seconds:
            self._safe_set_status(event, ExternalNotificationStatus.EXPIRED)
            return
        if not _event_notification_enabled(event, preferences):
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return

        try:
            message = self._renderer.render(event)
            speech_message = self._renderer.render_speech(event)
            channels = self._channel_policy.evaluate(event, preferences)
            if channels.silent:
                self._record_notification(
                    event,
                    message,
                    now,
                    NotificationInboxStatus.SILENT,
                )
                self._safe_set_status(event, ExternalNotificationStatus.SILENT)
                return
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
                last_notification_at=None,
                requires_proactive_enabled=False,
            )
        except Exception:
            self._logger.exception("External notification preparation failed.")
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return

        if not decision.allowed:
            inbox_record_id = self._record_notification(
                event,
                message,
                now,
                NotificationInboxStatus.SUPPRESSED,
            )
            self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            self._safe_set_inbox_status(
                inbox_record_id,
                NotificationInboxStatus.SUPPRESSED,
            )
            return

        last_notification_at = self._last_notification_at_by_kind.get(request.kind)
        eligible_at = now
        if last_notification_at is not None:
            cooldown_end = last_notification_at + timedelta(
                seconds=preferences.notification_cooldown_seconds
            )
            if cooldown_end > eligible_at:
                eligible_at = cooldown_end
        pending = PendingNotification(
            event=event,
            display_text=message,
            speech_text=speech_message,
            channels=channels,
            enqueued_at=now,
            eligible_at=eligible_at,
        )
        self._safe_set_status(event, ExternalNotificationStatus.QUEUED)
        if self._presentation_busy_provider() or eligible_at > now:
            enqueue_result = self._pending_queue.enqueue(pending)
            if enqueue_result.evicted is not None:
                self._record_notification(
                    enqueue_result.evicted.event,
                    enqueue_result.evicted.display_text,
                    now,
                    NotificationInboxStatus.SUPPRESSED,
                )
                self._safe_set_status(
                    enqueue_result.evicted.event,
                    ExternalNotificationStatus.SUPPRESSED,
                )
            if not enqueue_result.accepted:
                self._record_notification(
                    event,
                    message,
                    now,
                    NotificationInboxStatus.SUPPRESSED,
                )
                self._safe_set_status(event, ExternalNotificationStatus.SUPPRESSED)
            return
        self._publish_batch(PendingNotificationBatch((pending,)), now)

    def flush_pending(self) -> int:
        """Resume ready notifications through the existing proactive path."""
        now = self._now_provider()
        preferences = self._preference_provider()
        expired = self._pending_queue.expire(
            now=now,
            expiry_seconds=preferences.event_expiry_seconds,
        )
        for item in expired:
            self._safe_set_status(item.event, ExternalNotificationStatus.EXPIRED)
            self._record_notification(
                item.event,
                item.display_text,
                now,
                NotificationInboxStatus.EXPIRED,
            )
        batches = self._pending_queue.drain_ready(
            now=now,
            presentation_busy=self._presentation_busy_provider(),
            expiry_seconds=preferences.event_expiry_seconds,
        )
        for batch in batches:
            self._publish_batch(batch, now)
        return len(batches)

    @property
    def pending_count(self) -> int:
        """Return the bounded in-memory pending count for diagnostics."""
        return self._pending_queue.size

    def _publish_batch(
        self,
        batch: PendingNotificationBatch,
        now: datetime,
    ) -> None:
        first = batch.notifications[0]
        event = first.event
        request_kind = _notification_kind(event)
        message = (
            self._renderer.render_aggregate(event, batch.count)
            if batch.count > 1
            else first.display_text
        )
        speech_message = (
            self._renderer.render_aggregate_speech(event, batch.count)
            if batch.count > 1
            else first.speech_text
        )
        self._last_notification_at_by_kind[request_kind] = now
        inbox_record_id = self._record_notification(
            event,
            message,
            now,
            NotificationInboxStatus.PENDING,
            aggregate_count=batch.count,
        )
        for item in batch.notifications:
            self._pending_receipts[request_kind].append(
                _ReceiptLink(item.event, inbox_record_id)
            )
        payload = {
            "kind": request_kind,
            "message": message,
            "speech_message": speech_message,
            "speech_enabled": first.channels.voice,
            "visual_enabled": first.channels.tray,
            "chat_enabled": first.channels.chat,
            "urgency": _URGENCY_BY_PRIORITY[event.priority].value,
            "created_at": now.isoformat(),
            "source": "external_integration",
            "aggregate_count": batch.count,
        }
        if first.channels.tray or first.channels.chat:
            self._event_bus.publish(EventType.PROACTIVE_SUGGESTION_READY, payload)
        elif first.channels.voice:
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
        aggregate_count = payload.get("aggregate_count", 1)
        count = aggregate_count if isinstance(aggregate_count, int) else 1
        links = tuple(pending.popleft() for _ in range(min(count, len(pending))))
        if not pending:
            self._pending_receipts.pop(kind, None)
        delivered = payload.get("delivered") is True
        for link in links:
            self._safe_set_status(
                link.event,
                (
                    ExternalNotificationStatus.DELIVERED
                    if delivered
                    else ExternalNotificationStatus.SUPPRESSED
                ),
                notified_at=self._now_provider() if delivered else None,
            )
        for inbox_record_id in {
            link.inbox_record_id for link in links if link.inbox_record_id is not None
        }:
            self._safe_set_inbox_status(
                inbox_record_id,
                (
                    NotificationInboxStatus.DELIVERED
                    if delivered
                    else NotificationInboxStatus.SUPPRESSED
                ),
            )

    def _record_notification(
        self,
        event: ExternalEvent,
        message: str,
        created_at: datetime,
        status: NotificationInboxStatus,
        *,
        aggregate_count: int = 1,
    ) -> int | None:
        if self._inbox_repository is None:
            return None
        try:
            record_id = self._inbox_repository.add(
                SanitizedNotification(
                    service=event.service,
                    event_kind=event.kind,
                    priority=event.priority,
                    display_text=message,
                    occurred_at=event.occurred_at,
                    created_at=created_at,
                    status=status,
                    aggregate_count=aggregate_count,
                )
            )
        except Exception:
            self._logger.exception("Sanitized notification persistence failed.")
            return None
        try:
            retention_days = self._preference_provider().receipt_retention_days
            self._inbox_repository.prune(
                maximum_records=_MAXIMUM_NOTIFICATION_RECORDS,
                older_than=created_at - timedelta(days=retention_days),
            )
        except Exception:
            self._logger.exception("Sanitized notification retention failed.")
        return record_id

    def _safe_set_inbox_status(
        self,
        record_id: int | None,
        status: NotificationInboxStatus,
    ) -> None:
        if self._inbox_repository is None or record_id is None:
            return
        try:
            self._inbox_repository.update_status(record_id, status)
        except Exception:
            self._logger.exception(
                "Notification Center status update failed: %s",
                status.value,
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
        "discord.owner_mention": discord.notify_owner_mentions,
        "discord.owner_reply": discord.notify_owner_replies,
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
