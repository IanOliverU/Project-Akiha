"""Sanitized failures raised while evaluating action requests."""

from __future__ import annotations

from project_akiha.core.actions.models import ActionFailureCategory


class ActionValidationError(ValueError):
    """Reject an untrusted action request with a safe failure category."""

    def __init__(
        self,
        category: ActionFailureCategory,
        message: str,
    ) -> None:
        super().__init__(message)
        self.category = category
