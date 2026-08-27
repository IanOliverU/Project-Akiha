"""Fail-closed validation for provider-neutral external events."""

from __future__ import annotations

import re
from datetime import datetime

from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEvent,
    ExternalEventKind,
    ExternalEventPriority,
    ExternalService,
)

_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_SECRET_LIKE_TEXT = re.compile(
    r"(?i)(?:\b(?:access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
    r"authorization|password|session[_ -]?cookie)\b\s*[:=]|"
    r"\bbearer\s+[A-Za-z0-9._~-]{12,})"
)
_IDENTIFIER = re.compile(r"[A-Za-z0-9._:@/-]+\Z")
_SERVICE_PREFIX = {
    ExternalService.GMAIL: "gmail.",
    ExternalService.DISCORD: "discord.",
}


class ExternalEventValidationError(ValueError):
    """Raised when an external provider event is unsafe or malformed."""


class ExternalEventValidator:
    """Normalize one typed external event before it can reach the event bus."""

    def validate(self, candidate: ExternalEvent) -> ExternalEvent:
        """Return a bounded safe copy or fail closed."""
        if not isinstance(candidate, ExternalEvent):
            raise ExternalEventValidationError("External event type is invalid.")
        if not isinstance(candidate.service, ExternalService):
            raise ExternalEventValidationError("External service is invalid.")
        if not isinstance(candidate.kind, ExternalEventKind):
            raise ExternalEventValidationError("External event kind is invalid.")
        if not candidate.kind.value.startswith(_SERVICE_PREFIX[candidate.service]):
            raise ExternalEventValidationError(
                "External event kind does not match its service."
            )
        if not isinstance(candidate.classification, ExternalClassification):
            raise ExternalEventValidationError("External classification is invalid.")
        if not isinstance(candidate.priority, ExternalEventPriority):
            raise ExternalEventValidationError("External priority is invalid.")
        if not isinstance(candidate.occurred_at, datetime):
            raise ExternalEventValidationError("External event timestamp is invalid.")
        if candidate.occurred_at.tzinfo is None:
            raise ExternalEventValidationError(
                "External event timestamp must be timezone-aware."
            )

        external_id = _bounded_text(
            candidate.external_id,
            field="external_id",
            maximum=256,
            identifier=True,
        )
        sender_display = _optional_text(
            candidate.sender_display,
            field="sender_display",
            maximum=160,
        )
        subject = _optional_text(candidate.subject, field="subject", maximum=256)
        context_label = _optional_text(
            candidate.context_label,
            field="context_label",
            maximum=160,
        )
        return ExternalEvent(
            service=candidate.service,
            external_id=external_id,
            kind=candidate.kind,
            occurred_at=candidate.occurred_at,
            sender_display=sender_display,
            subject=subject,
            context_label=context_label,
            classification=candidate.classification,
            priority=candidate.priority,
        )


def _optional_text(value: str | None, *, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _bounded_text(value, field=field, maximum=maximum)


def _bounded_text(
    value: str,
    *,
    field: str,
    maximum: int,
    identifier: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ExternalEventValidationError(f"External {field} must be text.")
    if _CONTROL_CHARACTER.search(value) is not None:
        raise ExternalEventValidationError(
            f"External {field} contains control characters."
        )
    normalized = " ".join(value.split())
    if not normalized:
        raise ExternalEventValidationError(f"External {field} cannot be empty.")
    if len(normalized) > maximum:
        raise ExternalEventValidationError(f"External {field} is too long.")
    if _SECRET_LIKE_TEXT.search(normalized) is not None:
        raise ExternalEventValidationError(
            f"External {field} contains secret-like text."
        )
    if identifier and _IDENTIFIER.fullmatch(normalized) is None:
        raise ExternalEventValidationError("External identifier format is invalid.")
    return normalized
