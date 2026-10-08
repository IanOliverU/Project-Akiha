"""Policy-gated timer delivery through the existing inbox and presentation path."""

from __future__ import annotations

import logging

from project_akiha.core.behavior import (
    NotificationRequest,
    NotificationUrgency,
    ProactiveDeliveryRequest,
)
from project_akiha.core.notifications import NotificationInboxStatus
from project_akiha.core.utilities.timers import TimerStatus


class TimerDeliveryController:
    def __init__(
        self,
        service,
        *,
        inbox,
        notification_policy,
        activity_provider,
        delivery_controller,
        preference_provider,
        busy_provider,
        now_provider,
        logger=None,
    ) -> None:
        self.service = service
        self.inbox = inbox
        self.policy = notification_policy
        self.activity_provider = activity_provider
        self.delivery = delivery_controller
        self.preferences = preference_provider
        self.busy = busy_provider
        self.now = now_provider
        self.logger = logger or logging.getLogger("project_akiha.timers")

    def tick(self) -> None:
        if self.service is None:
            return
        try:
            records = self.service.tick()
        except Exception:
            self.logger.error("Timer polling unavailable.")
            return
        for record in records:
            if record.status is TimerStatus.MISSED:
                continue  # Recovery beyond the grace period: inbox only.
            try:
                self._deliver(record)
            except Exception:
                # Receipt already committed; never retry user-facing delivery.
                self.logger.error(
                    "Timer presentation unavailable; inspect Notification Center."
                )

    def _deliver(self, record) -> None:
        message = f"Timer {record.timer_id} elapsed."
        local_now = self.now()
        decision = self.policy.evaluate(
            NotificationRequest("timers.elapsed", message, NotificationUrgency.NORMAL),
            activity=self.activity_provider(),
            now=local_now,
            requires_proactive_enabled=False,
        )
        if not decision.allowed or self.busy():
            self.inbox.update_status(
                record.notification_id, NotificationInboxStatus.SUPPRESSED
            )
            return
        prefs = self.preferences()
        result = self.delivery.deliver_request(
            ProactiveDeliveryRequest(
                "timers.elapsed",
                message,
                NotificationUrgency.NORMAL,
                local_now,
                allow_chat=prefs.chat_notifications_enabled,
                allow_tray=prefs.visual_notifications_enabled,
            ),
            speech_enabled=prefs.voice_notifications_enabled,
        )
        self.inbox.update_status(
            record.notification_id,
            (
                NotificationInboxStatus.DELIVERED
                if result.delivered
                else NotificationInboxStatus.SILENT
            ),
        )
