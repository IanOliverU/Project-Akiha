"""Minimal Gmail REST client restricted to metadata synchronization."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GMAIL_API_BASE_URL = "https://gmail.googleapis.com/gmail/v1"
JsonTransport = Callable[[str, str, dict[str, str], float], dict[str, Any]]


class GmailApiError(RuntimeError):
    """Privacy-safe Gmail API failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GmailCursorExpired(GmailApiError):
    """Raised when Gmail no longer recognizes a stored history cursor."""


@dataclass(frozen=True, slots=True)
class GmailProfile:
    """Minimal mailbox identity and synchronization baseline."""

    account_key: str
    history_id: str


@dataclass(frozen=True, slots=True)
class GmailMessageMetadata:
    """Bounded message metadata allowed beyond the provider boundary."""

    message_id: str
    sender: str | None
    subject: str | None
    timestamp_ms: int
    label_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GmailHistoryPage:
    """One incremental Gmail history page."""

    message_ids: tuple[str, ...]
    history_id: str
    next_page_token: str | None


class GmailApiClient:
    """Call only profile, history, and metadata message endpoints."""

    def __init__(
        self,
        *,
        timeout_seconds: int,
        transport: JsonTransport | None = None,
    ) -> None:
        self._timeout_seconds = min(max(timeout_seconds, 1), 60)
        self._transport = transport or _request_json

    def apply_timeout(self, timeout_seconds: int) -> None:
        """Apply a validated request timeout without replacing the transport."""
        self._timeout_seconds = min(max(timeout_seconds, 1), 60)

    def get_profile(self, access_token: str) -> GmailProfile:
        """Return the account key and current history cursor."""
        payload = self._get("/users/me/profile", access_token)
        account_key = payload.get("emailAddress")
        history_id = payload.get("historyId")
        if not isinstance(account_key, str) or not account_key.strip():
            raise GmailApiError("malformed_response", "Gmail profile is invalid.")
        if not isinstance(history_id, str) or not history_id.isdecimal():
            raise GmailApiError("malformed_response", "Gmail history ID is invalid.")
        return GmailProfile(account_key.strip(), history_id)

    def list_history(
        self,
        access_token: str,
        start_history_id: str,
        *,
        page_token: str | None = None,
    ) -> GmailHistoryPage:
        """List only message-added history after a committed cursor."""
        query: dict[str, str | int] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": 100,
        }
        if page_token:
            query["pageToken"] = page_token
        try:
            payload = self._get(
                f"/users/me/history?{urlencode(query)}",
                access_token,
            )
        except GmailApiError as error:
            if error.code == "cursor_expired":
                raise GmailCursorExpired(error.code, str(error)) from error
            raise
        history_id = payload.get("historyId", start_history_id)
        next_page_token = payload.get("nextPageToken")
        history = payload.get("history", [])
        if not isinstance(history_id, str) or not history_id.isdecimal():
            raise GmailApiError("malformed_response", "Gmail history is invalid.")
        if next_page_token is not None and not isinstance(next_page_token, str):
            raise GmailApiError("malformed_response", "Gmail page token is invalid.")
        if not isinstance(history, list):
            raise GmailApiError("malformed_response", "Gmail history is invalid.")
        message_ids: list[str] = []
        for record in history:
            if not isinstance(record, dict):
                raise GmailApiError(
                    "malformed_response",
                    "Gmail history record is invalid.",
                )
            additions = record.get("messagesAdded", [])
            if not isinstance(additions, list):
                raise GmailApiError(
                    "malformed_response",
                    "Gmail message additions are invalid.",
                )
            for addition in additions:
                message_id = _message_id_from_addition(addition)
                if message_id not in message_ids:
                    message_ids.append(message_id)
        return GmailHistoryPage(
            message_ids=tuple(message_ids),
            history_id=history_id,
            next_page_token=next_page_token,
        )

    def get_message_metadata(
        self,
        access_token: str,
        message_id: str,
    ) -> GmailMessageMetadata:
        """Fetch headers and labels without a body or snippet."""
        query = urlencode(
            [
                ("format", "metadata"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "Date"),
            ]
        )
        payload = self._get(
            f"/users/me/messages/{message_id}?{query}",
            access_token,
        )
        returned_id = payload.get("id")
        internal_date = payload.get("internalDate", "0")
        label_ids = payload.get("labelIds", [])
        message_payload = payload.get("payload", {})
        if returned_id != message_id:
            raise GmailApiError("malformed_response", "Gmail message ID changed.")
        if not isinstance(internal_date, str) or not internal_date.isdecimal():
            raise GmailApiError("malformed_response", "Gmail timestamp is invalid.")
        if not isinstance(label_ids, list) or not all(
            isinstance(value, str) for value in label_ids
        ):
            raise GmailApiError("malformed_response", "Gmail labels are invalid.")
        if not isinstance(message_payload, dict):
            raise GmailApiError("malformed_response", "Gmail metadata is invalid.")
        headers = message_payload.get("headers", [])
        if not isinstance(headers, list):
            raise GmailApiError("malformed_response", "Gmail headers are invalid.")
        header_values = _allowed_headers(headers)
        return GmailMessageMetadata(
            message_id=message_id,
            sender=header_values.get("from"),
            subject=header_values.get("subject"),
            timestamp_ms=int(internal_date),
            label_ids=tuple(label_ids),
        )

    def _get(self, target: str, access_token: str) -> dict[str, Any]:
        token = access_token.strip()
        if not token:
            raise GmailApiError("authentication_failure", "Gmail is not authorized.")
        return self._transport(
            f"{GMAIL_API_BASE_URL}{target}",
            "GET",
            {"Accept": "application/json", "Authorization": f"Bearer {token}"},
            float(self._timeout_seconds),
        )


def _message_id_from_addition(addition: object) -> str:
    if not isinstance(addition, dict):
        raise GmailApiError("malformed_response", "Gmail message addition is invalid.")
    message = addition.get("message")
    if not isinstance(message, dict):
        raise GmailApiError("malformed_response", "Gmail message addition is invalid.")
    message_id = message.get("id")
    if not isinstance(message_id, str) or not message_id.strip():
        raise GmailApiError("malformed_response", "Gmail message ID is invalid.")
    return message_id.strip()


def _allowed_headers(headers: list[object]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for header in headers:
        if not isinstance(header, dict):
            continue
        name = header.get("name")
        value = header.get("value")
        if not isinstance(name, str) or not isinstance(value, str):
            continue
        normalized_name = name.casefold()
        if normalized_name in {"from", "subject", "date"}:
            normalized_value = " ".join(value.split())[:256]
            if normalized_value:
                allowed[normalized_name] = normalized_value
    return allowed


def _request_json(
    url: str,
    method: str,
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    request = Request(url, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        code = {
            401: "authentication_failure",
            403: "permission_failure",
            404: "cursor_expired" if "/history?" in url else "not_found",
            429: "rate_limited",
        }.get(error.code, "provider_unavailable")
        raise GmailApiError(
            code, f"Gmail request failed with HTTP {error.code}."
        ) from error
    except (OSError, URLError) as error:
        raise GmailApiError("network_failure", "Gmail could not be reached.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GmailApiError(
            "malformed_response",
            "Gmail returned an invalid response.",
        ) from error
    if not isinstance(payload, dict):
        raise GmailApiError("malformed_response", "Gmail response is invalid.")
    return payload
