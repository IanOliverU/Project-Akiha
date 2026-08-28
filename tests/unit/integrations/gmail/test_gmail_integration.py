"""Tests for metadata-only Gmail authorization and synchronization."""

from __future__ import annotations

import unittest
from datetime import datetime
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

from project_akiha.config import GmailIntegrationConfig
from project_akiha.core.integrations import (
    ExternalClassification,
    ExternalEventKind,
    ExternalService,
)
from project_akiha.integrations.gmail.auth import (
    GMAIL_METADATA_SCOPE,
    GmailAuthorizationCode,
    GmailOAuthError,
    create_gmail_authorization_session,
    exchange_gmail_authorization_code,
    parse_gmail_callback,
    refresh_gmail_access_token,
)
from project_akiha.integrations.gmail.classification import classify_gmail_metadata
from project_akiha.integrations.gmail.client import (
    GmailApiClient,
    GmailHistoryPage,
    GmailMessageMetadata,
    GmailProfile,
)
from project_akiha.integrations.gmail.provider import GmailIntegrationProvider


class GmailAuthorizationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = GmailIntegrationConfig(
            enabled=True,
            client_id="akiha.apps.googleusercontent.com",
        )

    def test_authorization_uses_only_metadata_scope_and_pkce(self) -> None:
        session = create_gmail_authorization_session(
            self.config,
            code_verifier="a" * 64,
            state="expected-state",
        )

        query = parse_qs(urlparse(session.authorization_url).query)
        self.assertEqual(query["scope"], [GMAIL_METADATA_SCOPE])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertNotIn("client_secret", query)

    def test_callback_rejects_wrong_state(self) -> None:
        with self.assertRaisesRegex(GmailOAuthError, "state"):
            parse_gmail_callback(
                "/callback?code=one&state=wrong",
                expected_state="expected",
                redirect_uri=self.config.redirect_uri,
            )

    def test_code_exchange_rejects_scope_expansion_or_missing_metadata(self) -> None:
        session = create_gmail_authorization_session(
            self.config,
            code_verifier="a" * 64,
            state="expected",
        )

        with self.assertRaisesRegex(GmailOAuthError, "metadata"):
            exchange_gmail_authorization_code(
                session,
                GmailAuthorizationCode("code"),
                timeout_seconds=5,
                transport=lambda *_args: {
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "expires_in": 3600,
                    "scope": "openid",
                },
            )

    def test_token_exchange_reports_invalid_desktop_client_without_raw_detail(
        self,
    ) -> None:
        session = create_gmail_authorization_session(
            self.config,
            code_verifier="a" * 64,
            state="expected",
        )
        response = BytesIO(
            b'{"error":"invalid_client","error_description":"private detail"}'
        )
        error = HTTPError(
            "https://oauth2.googleapis.com/token",
            401,
            "Unauthorized",
            {},
            response,
        )

        with patch(
            "project_akiha.integrations.gmail.auth.urlopen",
            side_effect=error,
        ):
            with self.assertRaisesRegex(GmailOAuthError, "Desktop app") as raised:
                exchange_gmail_authorization_code(
                    session,
                    GmailAuthorizationCode("code"),
                    timeout_seconds=5,
                )

        self.assertNotIn("private detail", str(raised.exception))

    def test_token_exchange_reports_invalid_grant_without_raw_detail(self) -> None:
        session = create_gmail_authorization_session(
            self.config,
            code_verifier="a" * 64,
            state="expected",
        )
        response = BytesIO(
            b'{"error":"invalid_grant","error_description":"private detail"}'
        )
        error = HTTPError(
            "https://oauth2.googleapis.com/token",
            400,
            "Bad Request",
            {},
            response,
        )

        with patch(
            "project_akiha.integrations.gmail.auth.urlopen",
            side_effect=error,
        ):
            with self.assertRaisesRegex(GmailOAuthError, "one-time") as raised:
                exchange_gmail_authorization_code(
                    session,
                    GmailAuthorizationCode("code"),
                    timeout_seconds=5,
                )

        self.assertNotIn("private detail", str(raised.exception))

    def test_token_exchange_identifies_non_desktop_client_safely(self) -> None:
        session = create_gmail_authorization_session(
            self.config,
            code_verifier="a" * 64,
            state="expected",
        )
        response = BytesIO(
            b'{"error":"invalid_request",'
            b'"error_description":"client_secret is missing."}'
        )
        error = HTTPError(
            "https://oauth2.googleapis.com/token",
            400,
            "Bad Request",
            {},
            response,
        )

        with patch(
            "project_akiha.integrations.gmail.auth.urlopen",
            side_effect=error,
        ):
            with self.assertRaisesRegex(GmailOAuthError, "Desktop app"):
                exchange_gmail_authorization_code(
                    session,
                    GmailAuthorizationCode("code"),
                    timeout_seconds=5,
                )

    def test_client_secret_is_sent_for_code_exchange_and_refresh(self) -> None:
        requests: list[dict[str, list[str]]] = []

        def transport(_url: str, data: bytes, _timeout: float):
            requests.append(parse_qs(data.decode("ascii")))
            return {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "scope": GMAIL_METADATA_SCOPE,
            }

        session = create_gmail_authorization_session(
            self.config,
            code_verifier="a" * 64,
            state="expected",
        )
        exchange_gmail_authorization_code(
            session,
            GmailAuthorizationCode("code"),
            client_secret="desktop-secret",
            timeout_seconds=5,
            transport=transport,
        )
        refresh_gmail_access_token(
            self.config,
            "refresh",
            client_secret="desktop-secret",
            transport=transport,
        )

        self.assertEqual(requests[0]["client_secret"], ["desktop-secret"])
        self.assertEqual(requests[1]["client_secret"], ["desktop-secret"])


class GmailClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.requests: list[tuple[str, str, dict[str, str], float]] = []

    def test_fetches_only_allowed_metadata_headers(self) -> None:
        def transport(url, method, headers, timeout):
            self.requests.append((url, method, headers, timeout))
            return {
                "id": "message-1",
                "internalDate": "1787817600000",
                "labelIds": ["INBOX", "IMPORTANT"],
                "snippet": "must never cross the client boundary",
                "payload": {
                    "headers": [
                        {"name": "From", "value": "Recruiter <r@example.test>"},
                        {"name": "Subject", "value": "Interview invitation"},
                        {"name": "X-Secret", "value": "private"},
                    ],
                    "body": {"data": "forbidden"},
                },
            }

        client = GmailApiClient(timeout_seconds=5, transport=transport)
        metadata = client.get_message_metadata("access-token", "message-1")

        self.assertEqual(metadata.subject, "Interview invitation")
        self.assertEqual(metadata.sender, "Recruiter <r@example.test>")
        self.assertFalse(hasattr(metadata, "snippet"))
        self.assertFalse(hasattr(metadata, "body"))
        request_url = self.requests[0][0]
        self.assertIn("format=metadata", request_url)
        self.assertIn("metadataHeaders=From", request_url)
        self.assertNotIn("format=full", request_url)

    def test_history_deduplicates_message_ids(self) -> None:
        client = GmailApiClient(
            timeout_seconds=5,
            transport=lambda *_args: {
                "historyId": "12",
                "history": [
                    {
                        "messagesAdded": [
                            {"message": {"id": "a"}},
                            {"message": {"id": "a"}},
                            {"message": {"id": "b"}},
                        ]
                    }
                ],
            },
        )

        page = client.list_history("access", "10")

        self.assertEqual(page.message_ids, ("a", "b"))


class GmailClassificationTest(unittest.TestCase):
    def test_bounded_classification_is_local_and_best_effort(self) -> None:
        cases = (
            ("Interview schedule", (), ExternalClassification.INTERVIEW),
            ("Talent acquisition update", (), ExternalClassification.RECRUITER),
            ("Status", ("IMPORTANT",), ExternalClassification.IMPORTANT),
            ("Weekly newsletter", (), ExternalClassification.NEWSLETTER),
            ("Limited sale", (), ExternalClassification.PROMOTIONAL),
            ("Hello", ("CATEGORY_PERSONAL",), ExternalClassification.PERSONAL),
        )
        for subject, labels, expected in cases:
            with self.subTest(subject=subject):
                result = classify_gmail_metadata(
                    GmailMessageMetadata("id", None, subject, 1, labels)
                )
                self.assertEqual(result.classification, expected)


class GmailProviderTest(unittest.TestCase):
    def test_first_poll_establishes_cursor_without_replaying_mail(self) -> None:
        repository = _Repository()
        provider = GmailIntegrationProvider(
            GmailIntegrationConfig(
                enabled=True,
                client_id="akiha.apps.googleusercontent.com",
            ),
            _Session(),
            _Client(),
            repository,
        )
        events = []
        provider._on_event = events.append

        provider._poll_once()

        self.assertEqual(events, [])
        self.assertEqual(repository.saved[-1][2], "10")

    def test_incremental_poll_emits_metadata_event_and_commits_cursor(self) -> None:
        repository = _Repository(cursor="10")
        provider = GmailIntegrationProvider(
            GmailIntegrationConfig(
                enabled=True,
                client_id="akiha.apps.googleusercontent.com",
            ),
            _Session(),
            _Client(),
            repository,
        )
        events = []
        provider._on_event = events.append

        provider._poll_once()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].service, ExternalService.GMAIL)
        self.assertEqual(events[0].kind, ExternalEventKind.GMAIL_INTERVIEW_CANDIDATE)
        self.assertEqual(repository.saved[-1][2], "11")


class _Session:
    def access_token(self) -> str:
        return "access"

    def apply_config(self, _config: GmailIntegrationConfig) -> None:
        return None

    def clear(self) -> None:
        return None


class _Client:
    def apply_timeout(self, _timeout: int) -> None:
        return None

    def get_profile(self, _token: str) -> GmailProfile:
        return GmailProfile("ian@example.test", "10")

    def list_history(
        self,
        _token: str,
        _cursor: str,
        *,
        page_token: str | None = None,
    ) -> GmailHistoryPage:
        del page_token
        return GmailHistoryPage(("message-1",), "11", None)

    def get_message_metadata(
        self,
        _token: str,
        message_id: str,
    ) -> GmailMessageMetadata:
        return GmailMessageMetadata(
            message_id,
            "Example Recruiter",
            "Interview invitation",
            1_787_817_600_000,
            ("INBOX",),
        )


class _Repository:
    def __init__(self, cursor: str | None = None) -> None:
        self.cursor = cursor
        self.saved: list[tuple[ExternalService, str, str]] = []

    def load_sync_cursor(self, _service, _account_key):
        return self.cursor

    def save_sync_cursor(
        self,
        service,
        account_key,
        cursor,
        *,
        synchronized_at: datetime,
    ) -> None:
        del synchronized_at
        self.saved.append((service, account_key, cursor))

    def claim_event(self, *_args, **_kwargs):
        return True

    def set_notification_status(self, *_args, **_kwargs):
        return None

    def prune_receipts(self, **_kwargs):
        return 0

    def clear_service_data(self, _service):
        return None


if __name__ == "__main__":
    unittest.main()
