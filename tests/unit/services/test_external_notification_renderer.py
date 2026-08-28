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
    """Verify display and speech wording remain separate and bounded."""

    def test_interview_classification_is_presented_as_best_effort(self) -> None:
        renderer = ExternalNotificationRenderer()
        event = ExternalEvent(
            service=ExternalService.GMAIL,
            external_id="gmail-1",
            kind=ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE,
            occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
            sender_display="Example Recruiter",
            classification=ExternalClassification.INTERVIEW,
        )

        message = renderer.render(event)
        speech = renderer.render_speech(event)

        self.assertIn("Example Recruiter", message)
        self.assertIn("appears", message)
        self.assertIn("Ian-sama", speech)

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

        self.assertEqual(message, "A Friend mentioned Akiha Bot on Discord.")
        self.assertNotIn("message body", message)

    def test_owner_and_dm_desktop_text_is_english(self) -> None:
        renderer = ExternalNotificationRenderer()
        owner_mention = renderer.render(
            ExternalEvent(
                service=ExternalService.DISCORD,
                external_id="discord-2",
                kind=ExternalEventKind.DISCORD_OWNER_MENTION,
                occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                sender_display="A Friend",
            )
        )
        direct_message = renderer.render(
            ExternalEvent(
                service=ExternalService.DISCORD,
                external_id="discord-3",
                kind=ExternalEventKind.DISCORD_BOT_DIRECT_MESSAGE,
                occurred_at=datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
                sender_display="A Friend",
            )
        )

        self.assertEqual(owner_mention, "A Friend mentioned you on Discord.")
        self.assertEqual(
            direct_message,
            "A Friend sent Akiha Bot a direct message.",
        )


if __name__ == "__main__":
    unittest.main()
