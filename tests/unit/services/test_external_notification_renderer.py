"""Tests for local external-notification wording."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalService,
)
from project_akiha.services.external_notification_renderer import (
    ExternalNotificationRenderer,
)


class ExternalNotificationRendererTest(unittest.TestCase):
    """Verify wording is deterministic, bounded, and uncertainty-aware."""

    def test_interview_classification_is_presented_as_best_effort(self) -> None:
        message = ExternalNotificationRenderer().render(
            ExternalEvent(
                service=ExternalService.GMAIL,
                external_id="gmail-1",
                kind=ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
                occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                sender_display="Example Recruiter",
                classification=ExternalClassification.INTERVIEW,
            )
        )

        self.assertIn("Example Recruiter", message)
        self.assertIn("ようです", message)

    def test_discord_mention_is_identified_without_message_content(self) -> None:
        message = ExternalNotificationRenderer().render(
            ExternalEvent(
                service=ExternalService.DISCORD,
                external_id="discord-1",
                kind=ExternalEventKind.DISCORD_MENTION,
                occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                sender_display="A Friend",
            )
        )

        self.assertIn("Discord", message)
        self.assertIn("メンション", message)
        self.assertNotIn("message body", message)


if __name__ == "__main__":
    unittest.main()
