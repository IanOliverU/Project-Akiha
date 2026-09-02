"""Tests for explicit per-event notification channels."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.config import (
    DiscordIntegrationConfig,
    ExternalIntegrationsConfig,
    GmailIntegrationConfig,
)
from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.services.external_notification_channel_policy import (
    ExternalNotificationChannelPolicy,
)


class ExternalNotificationChannelPolicyTest(unittest.TestCase):
    def test_important_gmail_uses_important_mode(self) -> None:
        config = ExternalIntegrationsConfig(
            gmail=GmailIntegrationConfig(important_channel_mode="voice_only")
        )

        decision = ExternalNotificationChannelPolicy().evaluate(
            _event(),
            config,
        )

        self.assertFalse(decision.tray)
        self.assertFalse(decision.chat)
        self.assertTrue(decision.voice)

    def test_discord_category_uses_its_own_mode_and_global_gates(self) -> None:
        config = ExternalIntegrationsConfig(
            visual_notifications_enabled=False,
            discord=DiscordIntegrationConfig(mention_channel_mode="visual_chat_voice"),
        )

        decision = ExternalNotificationChannelPolicy().evaluate(
            _event(
                service=ExternalService.DISCORD,
                kind=ExternalEventKind.DISCORD_OWNER_MENTION,
                classification=ExternalClassification.GENERAL,
            ),
            config,
        )

        self.assertFalse(decision.tray)
        self.assertTrue(decision.chat)
        self.assertTrue(decision.voice)

    def test_silent_priority_cannot_be_reenabled_by_configuration(self) -> None:
        decision = ExternalNotificationChannelPolicy().evaluate(
            _event(priority=ExternalEventPriority.SILENT),
            ExternalIntegrationsConfig(),
        )

        self.assertTrue(decision.silent)


def _event(**changes: object) -> ExternalEvent:
    values: dict[str, object] = {
        "service": ExternalService.GMAIL,
        "external_id": "event-1",
        "kind": ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
        "occurred_at": datetime(2026, 9, 2, tzinfo=UTC),
        "classification": ExternalClassification.INTERVIEW,
        "priority": ExternalEventPriority.IMPORTANT,
    }
    values.update(changes)
    return ExternalEvent(**values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
