"""Convert explicit user action commands into typed assistant requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    ActionResult,
)
from project_akiha.core.actions.registry import (
    FILE_SEARCH_ACTION,
    OPEN_DIRECTORY_ACTION,
)
from project_akiha.services.assistant_actions import AssistantActionService

_OPEN_DIRECTORY_PATTERN = re.compile(
    r"^(?:(?:/open-dir)\s+|(?:open\s+(?:directory|folder))\s*[:=]\s*)" r"(?P<path>.+)$",
    re.IGNORECASE,
)
_SEARCH_FILES_PATTERN = re.compile(
    r"^(?:(?:/search-files)\s+|(?:search\s+files)\s*[:=]\s*)"
    r"(?P<query>[^|]+?)\s*\|\s*(?P<root>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AssistantActionDispatch:
    """Pair one user-originated typed request with its sanitized result."""

    request: ActionRequest
    result: ActionResult


class AssistantActionRequestParser:
    """Parse only explicit, unambiguous action command forms."""

    def parse(
        self, text: str, *, correlation_id: str | None = None
    ) -> ActionRequest | None:
        """Return a typed request for a supported command, otherwise ``None``."""
        normalized = text.strip()
        if not normalized:
            return None
        request_id = correlation_id or f"chat-action-{uuid4().hex}"

        open_match = _OPEN_DIRECTORY_PATTERN.fullmatch(normalized)
        if open_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=OPEN_DIRECTORY_ACTION,
                parameters={"path": open_match.group("path").strip()},
            )

        search_match = _SEARCH_FILES_PATTERN.fullmatch(normalized)
        if search_match is not None:
            return _request(
                correlation_id=request_id,
                action_id=FILE_SEARCH_ACTION,
                parameters={
                    "query": search_match.group("query").strip(),
                    "root": search_match.group("root").strip(),
                },
            )
        return None


class AssistantActionBridge:
    """Dispatch parsed user requests through the existing action service."""

    def __init__(
        self,
        action_service: AssistantActionService,
        parser: AssistantActionRequestParser | None = None,
    ) -> None:
        self._action_service = action_service
        self._parser = parser or AssistantActionRequestParser()

    def parse_user_text(
        self,
        text: str,
        *,
        correlation_id: str | None = None,
    ) -> ActionRequest | None:
        """Parse only user text; provider responses are never accepted here."""
        return self._parser.parse(text, correlation_id=correlation_id)

    async def dispatch(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> AssistantActionDispatch:
        """Evaluate one already-parsed request through validation and policy."""
        if not isinstance(request, ActionRequest):
            raise TypeError("assistant action bridge requires a typed request.")
        result = await self._action_service.evaluate_request(
            request,
            confirmed=confirmed,
            cancellation_token=cancellation_token,
        )
        return AssistantActionDispatch(request=request, result=result)


def _request(
    *,
    correlation_id: str,
    action_id: str,
    parameters: dict[str, object],
) -> ActionRequest:
    return ActionRequest(
        correlation_id=correlation_id,
        action_id=action_id,
        source="chat",
        parameters=parameters,
    )
