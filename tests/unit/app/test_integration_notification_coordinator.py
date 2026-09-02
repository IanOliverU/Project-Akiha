"""Tests for policy-gated external integration notifications."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from project_akiha.app.integration_notification_coordinator import (
    IntegrationNotificationCoordinator,
)
from project_akiha.config import BehaviorConfig, ExternalIntegrationsConfig
from project_akiha.core.behavior import (
    ActivitySnapshot,
    ActivityState,
    NotificationPolicy,
)
from project_akiha.core.events import Event, EventBus, EventType
from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalNotificationStatus,
    ExternalService,
)
from project_akiha.core.notifications import (
    NotificationInboxStatus,
    SanitizedNotification,
)
from project_akiha.services.external_event_validation import ExternalEventValidator
from project_akiha.services.external_notification_renderer import (
    ExternalNotificationRenderer,
)


class IntegrationNotificationCoordinatorTest(unittest.TestCase):
    """Verify validation, dedupe, app-thread handoff, and policy reuse."""

    def setUp(self) -> None:
        self.now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
        self.bus = EventBus()
        self.repository = _Repository()
        self.scheduled: list[object] = []
        self.accepted: list[Event] = []
        self.notifications: list[Event] = []
        self.bus.subscribe(EventType.EXTERNAL_EVENT_ACCEPTED, self.accepted.append)
        self.bus.subscribe(
            EventType.PROACTIVE_SUGGESTION_READY,
            self.notifications.append,
        )

    def test_valid_event_crosses_bus_only_after_app_thread_handoff(self) -> None:
        coordinator = self._coordinator()

        result = coordinator.submit(_event())

        self.assertEqual(result, "scheduled")
        self.assertEqual(self.accepted, [])
        self.assertEqual(self.notifications, [])
        self.assertEqual(len(self.scheduled), 1)

        self._run_scheduled()

        self.assertEqual(len(self.accepted), 1)
        self.assertEqual(len(self.notifications), 1)
        accepted_payload = self.accepted[0].payload
        self.assertNotIn("external_id", accepted_payload)
        self.assertNotIn("sender_display", accepted_payload)
        self.assertNotIn("subject", accepted_payload)
        self.assertTrue(accepted_payload["sender_present"])
        self.assertEqual(
            self.notifications[0].payload["kind"],
            "external.gmail.interview_candidate",
        )
        self.assertEqual(
            self.repository.statuses,
            [ExternalNotificationStatus.QUEUED],
        )

    def test_duplicate_is_not_scheduled_or_published(self) -> None:
        self.repository.claimed = False

        result = self._coordinator().submit(_event())

        self.assertEqual(result, "duplicate")
        self.assertEqual(self.scheduled, [])
        self.assertEqual(self.accepted, [])

    def test_invalid_event_fails_before_repository_or_bus(self) -> None:
        invalid = _event(kind=ExternalEventKind.DISCORD_MENTION)

        result = self._coordinator().submit(invalid)

        self.assertEqual(result, "invalid")
        self.assertEqual(self.repository.claim_calls, 0)
        self.assertEqual(self.scheduled, [])

    def test_disabled_behavior_policy_can_suppress_delivery(self) -> None:
        coordinator = self._coordinator(behavior_enabled=False)

        coordinator.submit(_event())
        self._run_scheduled()

        self.assertEqual(len(self.accepted), 1)
        self.assertEqual(self.notifications, [])
        self.assertEqual(
            self.repository.statuses,
            [ExternalNotificationStatus.SUPPRESSED],
        )

    def test_proactive_check_in_toggle_does_not_disable_integrations(self) -> None:
        coordinator = self._coordinator(proactive_enabled=False)

        coordinator.submit(_event())
        self._run_scheduled()

        self.assertEqual(len(self.notifications), 1)

    def test_cooldown_defers_same_kind_without_blocking_other_kind(self) -> None:
        coordinator = self._coordinator(
            preferences=ExternalIntegrationsConfig(
                notification_cooldown_seconds=1,
            )
        )
        coordinator.submit(_event(external_id="gmail-1"))
        self._run_scheduled()
        coordinator.submit(_event(external_id="gmail-2"))
        self._run_scheduled()
        coordinator.submit(
            _event(
                service=ExternalService.DISCORD,
                external_id="discord-1",
                kind=ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE,
                subject=None,
                classification=ExternalClassification.GENERAL,
                priority=ExternalEventPriority.NORMAL,
            )
        )
        self._run_scheduled()

        self.assertEqual(len(self.notifications), 2)
        self.assertEqual(
            self.repository.statuses,
            [
                ExternalNotificationStatus.QUEUED,
                ExternalNotificationStatus.QUEUED,
                ExternalNotificationStatus.QUEUED,
            ],
        )
        self.assertEqual(coordinator.pending_count, 1)

    def test_silent_event_is_receipted_without_rendering(self) -> None:
        coordinator = self._coordinator()

        coordinator.submit(_event(priority=ExternalEventPriority.SILENT))
        self._run_scheduled()

        self.assertEqual(len(self.accepted), 1)
        self.assertEqual(self.notifications, [])
        self.assertEqual(
            self.repository.statuses,
            [ExternalNotificationStatus.SILENT],
        )

    def test_repository_failure_fails_closed(self) -> None:
        self.repository.raise_on_claim = True

        with self.assertLogs("project_akiha.integrations", level="ERROR"):
            result = self._coordinator().submit(_event())

        self.assertEqual(result, "repository_error")
        self.assertEqual(self.scheduled, [])

    def test_expired_event_is_receipted_without_delivery(self) -> None:
        coordinator = self._coordinator()

        coordinator.submit(
            _event(occurred_at=datetime(2026, 8, 27, 11, 50, tzinfo=UTC))
        )
        self._run_scheduled()

        self.assertEqual(self.notifications, [])
        self.assertEqual(self.repository.statuses, [ExternalNotificationStatus.EXPIRED])

    def test_delivery_result_completes_receipt(self) -> None:
        coordinator = self._coordinator()
        coordinator.submit(_event())
        self._run_scheduled()

        self.bus.publish(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            {
                **self.notifications[0].payload,
                "delivered": True,
                "channel": "chat_notice",
            },
        )

        self.assertEqual(
            self.repository.statuses,
            [
                ExternalNotificationStatus.QUEUED,
                ExternalNotificationStatus.DELIVERED,
            ],
        )

    def test_disabled_delivery_channels_are_recorded_as_silent(self) -> None:
        coordinator = self._coordinator(
            preferences=ExternalIntegrationsConfig(
                visual_notifications_enabled=False,
                chat_notifications_enabled=False,
                voice_notifications_enabled=False,
            )
        )

        coordinator.submit(_event())
        self._run_scheduled()

        self.assertEqual(self.notifications, [])
        self.assertEqual(
            self.repository.statuses,
            [ExternalNotificationStatus.SILENT],
        )

    def test_busy_notifications_aggregate_into_one_sanitized_inbox_record(
        self,
    ) -> None:
        busy = [True]
        inbox = _InboxRepository()
        coordinator = self._coordinator(
            inbox_repository=inbox,
            presentation_busy_provider=lambda: busy[0],
        )
        coordinator.submit(_event(external_id="gmail-1"))
        self._run_scheduled()
        coordinator.submit(_event(external_id="gmail-2"))
        self._run_scheduled()

        self.assertEqual(coordinator.pending_count, 2)
        self.assertEqual(inbox.added, [])

        busy[0] = False
        self.now += timedelta(seconds=1)
        self.assertEqual(coordinator.flush_pending(), 1)

        self.assertEqual(len(self.notifications), 1)
        self.assertEqual(self.notifications[0].payload["aggregate_count"], 2)
        self.assertEqual(len(inbox.added), 1)
        self.assertEqual(inbox.added[0].aggregate_count, 2)
        self.assertEqual(inbox.prune_calls, 1)

        self.bus.publish(
            EventType.PROACTIVE_SUGGESTION_DELIVERED,
            {
                **self.notifications[0].payload,
                "delivered": True,
                "channel": "chat_notice",
            },
        )
        self.assertEqual(inbox.statuses, [(1, NotificationInboxStatus.DELIVERED)])

    def _coordinator(
        self,
        *,
        behavior_enabled: bool = True,
        proactive_enabled: bool = True,
        preferences: ExternalIntegrationsConfig | None = None,
        inbox_repository: object | None = None,
        presentation_busy_provider: object | None = None,
    ) -> IntegrationNotificationCoordinator:
        return IntegrationNotificationCoordinator(
            event_bus=self.bus,
            validator=ExternalEventValidator(),
            repository=self.repository,
            notification_policy=NotificationPolicy(
                BehaviorConfig(
                    enabled=behavior_enabled,
                    proactive_enabled=proactive_enabled,
                    minimum_seconds_between_notifications=60,
                )
            ),
            renderer=ExternalNotificationRenderer(),
            activity_provider=lambda: ActivitySnapshot(
                state=ActivityState.ACTIVE,
                idle_seconds=0,
                last_activity_at=self.now,
                source="test",
            ),
            schedule_on_app_thread=self.scheduled.append,
            now_provider=lambda: self.now,
            preference_provider=(lambda: preferences or ExternalIntegrationsConfig()),
            inbox_repository=inbox_repository,  # type: ignore[arg-type]
            presentation_busy_provider=presentation_busy_provider,  # type: ignore[arg-type]
        )

    def _run_scheduled(self) -> None:
        callback = self.scheduled.pop(0)
        assert callable(callback)
        callback()


class _Repository:
    def __init__(self) -> None:
        self.claimed = True
        self.raise_on_claim = False
        self.claim_calls = 0
        self.statuses: list[ExternalNotificationStatus] = []
        self.prune_calls = 0

    def claim_event(self, event: ExternalEvent, *, received_at: datetime) -> bool:
        del event, received_at
        self.claim_calls += 1
        if self.raise_on_claim:
            raise RuntimeError("database unavailable")
        return self.claimed

    def set_notification_status(
        self,
        event: ExternalEvent,
        status: ExternalNotificationStatus,
        *,
        notified_at: datetime | None = None,
    ) -> None:
        del event, notified_at
        self.statuses.append(status)

    def load_sync_cursor(
        self,
        service: ExternalService,
        account_key: str,
    ) -> str | None:
        del service, account_key
        return None

    def save_sync_cursor(
        self,
        service: ExternalService,
        account_key: str,
        cursor: str,
        *,
        synchronized_at: datetime,
    ) -> None:
        del service, account_key, cursor, synchronized_at

    def prune_receipts(self, *, older_than: datetime) -> int:
        del older_than
        self.prune_calls += 1
        return 0

    def clear_service_data(self, service: ExternalService) -> None:
        del service


class _InboxRepository:
    def __init__(self) -> None:
        self.added: list[SanitizedNotification] = []
        self.statuses: list[tuple[int, NotificationInboxStatus]] = []
        self.prune_calls = 0

    def add(self, notification: SanitizedNotification) -> int:
        self.added.append(notification)
        return len(self.added)

    def update_status(
        self,
        record_id: int,
        status: NotificationInboxStatus,
    ) -> None:
        self.statuses.append((record_id, status))

    def prune(self, *, maximum_records: int, older_than: datetime) -> int:
        self.prune_calls += 1
        self.last_maximum_records = maximum_records
        self.last_older_than = older_than
        return 0


def _event(**changes: object) -> ExternalEvent:
    values: dict[str, object] = {
        "service": ExternalService.GMAIL,
        "external_id": "gmail-message-123",
        "kind": ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
        "occurred_at": datetime(2026, 8, 27, 11, 59, tzinfo=UTC),
        "sender_display": "Example Recruiter",
        "subject": "Interview schedule",
        "context_label": "Inbox",
        "classification": ExternalClassification.INTERVIEW,
        "priority": ExternalEventPriority.IMPORTANT,
    }
    values.update(changes)
    return ExternalEvent(**values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
