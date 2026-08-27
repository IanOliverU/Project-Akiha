"""Tests for the external-event validation and redaction boundary."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)
from project_akiha.services.external_event_validation import (
    ExternalEventValidationError,
    ExternalEventValidator,
)


class ExternalEventValidatorTest(unittest.TestCase):
    """Verify unsafe provider payloads fail before reaching the event bus."""

    def setUp(self) -> None:
        self.validator = ExternalEventValidator()

    def test_normalizes_bounded_display_metadata(self) -> None:
        event = self.validator.validate(
            _event(sender_display="  Example   Recruiter  ")
        )

        self.assertEqual(event.sender_display, "Example Recruiter")
        self.assertEqual(event.external_id, "message-123")

    def test_rejects_kind_from_another_service(self) -> None:
        with self.assertRaisesRegex(
            ExternalEventValidationError,
            "does not match",
        ):
            self.validator.validate(_event(kind=ExternalEventKind.DISCORD_MENTION))

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(
            ExternalEventValidationError,
            "timezone-aware",
        ):
            self.validator.validate(_event(occurred_at=datetime(2026, 8, 27, 12, 0)))

    def test_rejects_control_characters_before_normalization(self) -> None:
        with self.assertRaisesRegex(
            ExternalEventValidationError,
            "control characters",
        ):
            self.validator.validate(_event(subject="Line one\nLine two"))

    def test_rejects_secret_like_metadata(self) -> None:
        with self.assertRaisesRegex(
            ExternalEventValidationError,
            "secret-like",
        ):
            self.validator.validate(
                _event(subject="Authorization: Bearer private-token-value")
            )

    def test_rejects_invalid_external_identifier(self) -> None:
        with self.assertRaisesRegex(
            ExternalEventValidationError,
            "identifier format",
        ):
            self.validator.validate(_event(external_id="message id with spaces"))

    def test_rejects_untyped_candidate(self) -> None:
        with self.assertRaisesRegex(
            ExternalEventValidationError,
            "type is invalid",
        ):
            self.validator.validate({"service": "gmail"})  # type: ignore[arg-type]


def _event(**changes: object) -> ExternalEvent:
    values: dict[str, object] = {
        "service": ExternalService.GMAIL,
        "external_id": "message-123",
        "kind": ExternalEventKind.GMAIL_NEW_MESSAGE,
        "occurred_at": datetime(2026, 8, 27, 12, 0, tzinfo=UTC),
        "sender_display": "Example Sender",
        "subject": "Interview schedule",
        "context_label": "Inbox",
        "classification": ExternalClassification.INTERVIEW,
        "priority": ExternalEventPriority.IMPORTANT,
    }
    values.update(changes)
    return ExternalEvent(**values)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
