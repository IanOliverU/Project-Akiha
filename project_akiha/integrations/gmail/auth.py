"""Google Desktop OAuth with PKCE for metadata-only Gmail access."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from project_akiha.config import GmailIntegrationConfig

GMAIL_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_METADATA_SCOPE = "https://www.googleapis.com/auth/gmail.metadata"

TokenTransport = Callable[[str, bytes, float], dict[str, Any]]
_PKCE_VERIFIER_PATTERN = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z")


class GmailOAuthError(RuntimeError):
    """Raised when Gmail authorization cannot complete safely."""


@dataclass(frozen=True, slots=True)
class GmailAuthorizationSession:
    """Short-lived values for one browser authorization attempt."""

    authorization_url: str
    client_id: str
    redirect_uri: str
    state: str
    code_verifier: str


@dataclass(frozen=True, slots=True)
class GmailAuthorizationCode:
    """Validated one-time code returned to the loopback callback."""

    code: str


@dataclass(frozen=True, slots=True)
class GmailToken:
    """Short-lived access token and DPAPI-bound refresh credential."""

    access_token: str
    refresh_token: str
    expires_at: float
    scopes: tuple[str, ...]


def create_gmail_authorization_session(
    config: GmailIntegrationConfig,
    *,
    code_verifier: str | None = None,
    state: str | None = None,
) -> GmailAuthorizationSession:
    """Create a least-privilege desktop OAuth authorization URL."""
    if not config.enabled:
        raise GmailOAuthError("Gmail integration is disabled.")
    verifier = code_verifier or secrets.token_urlsafe(64)
    if _PKCE_VERIFIER_PATTERN.fullmatch(verifier) is None:
        raise GmailOAuthError("The Gmail PKCE verifier has an invalid format.")
    state_token = state or secrets.token_urlsafe(32)
    if not state_token:
        raise GmailOAuthError("The Gmail authorization state is empty.")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    query = urlencode(
        {
            "client_id": config.client_id.strip(),
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": GMAIL_METADATA_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state_token,
        }
    )
    return GmailAuthorizationSession(
        authorization_url=f"{GMAIL_AUTHORIZE_URL}?{query}",
        client_id=config.client_id.strip(),
        redirect_uri=config.redirect_uri,
        state=state_token,
        code_verifier=verifier,
    )


def parse_gmail_callback(
    request_target: str,
    *,
    expected_state: str,
    redirect_uri: str,
) -> GmailAuthorizationCode:
    """Validate callback path, CSRF state, and one-time code."""
    expected = urlparse(redirect_uri)
    callback = urlparse(request_target)
    if callback.path != expected.path:
        raise GmailOAuthError("Google returned to an unexpected callback path.")
    query = parse_qs(callback.query, keep_blank_values=True)
    if _single_query_value(query, "state") != expected_state:
        raise GmailOAuthError("Gmail authorization state validation failed.")
    provider_error = _single_query_value(query, "error", required=False)
    if provider_error is not None:
        if provider_error == "access_denied":
            raise GmailOAuthError("Gmail authorization was cancelled.")
        raise GmailOAuthError("Google declined Gmail authorization.")
    code = _single_query_value(query, "code")
    if not code:
        raise GmailOAuthError("Google did not return an authorization code.")
    return GmailAuthorizationCode(code)


def exchange_gmail_authorization_code(
    session: GmailAuthorizationSession,
    code: GmailAuthorizationCode,
    *,
    timeout_seconds: float,
    transport: TokenTransport | None = None,
    now: Callable[[], float] = time.time,
) -> GmailToken:
    """Exchange a validated PKCE code for metadata-only Gmail tokens."""
    payload = _exchange_token(
        {
            "grant_type": "authorization_code",
            "code": code.code,
            "redirect_uri": session.redirect_uri,
            "client_id": session.client_id,
            "code_verifier": session.code_verifier,
        },
        timeout_seconds=timeout_seconds,
        transport=transport,
    )
    return _parse_token(payload, now=now, require_refresh_token=True)


def refresh_gmail_access_token(
    config: GmailIntegrationConfig,
    refresh_token: str,
    *,
    transport: TokenTransport | None = None,
    now: Callable[[], float] = time.time,
) -> GmailToken:
    """Refresh Gmail access while preserving a non-rotated refresh token."""
    normalized = refresh_token.strip()
    if not normalized:
        raise GmailOAuthError("The saved Gmail authorization is empty.")
    payload = _exchange_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": normalized,
            "client_id": config.client_id.strip(),
        },
        timeout_seconds=config.request_timeout_seconds,
        transport=transport,
    )
    parsed = _parse_token(payload, now=now, require_refresh_token=False)
    return GmailToken(
        access_token=parsed.access_token,
        refresh_token=parsed.refresh_token or normalized,
        expires_at=parsed.expires_at,
        scopes=parsed.scopes or (GMAIL_METADATA_SCOPE,),
    )


def _exchange_token(
    fields: dict[str, str],
    *,
    timeout_seconds: float,
    transport: TokenTransport | None,
) -> dict[str, Any]:
    encoded = urlencode(fields).encode("ascii")
    return (transport or _post_token)(
        GMAIL_TOKEN_URL,
        encoded,
        min(max(timeout_seconds, 1.0), 60.0),
    )


def _post_token(url: str, data: bytes, timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code in {400, 401}:
            detail = "Google rejected Gmail authorization. Please connect again."
        elif error.code == 429:
            detail = "Google temporarily rate-limited Gmail authorization."
        else:
            detail = f"Gmail authorization returned HTTP {error.code}."
        raise GmailOAuthError(detail) from error
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GmailOAuthError(
            "Gmail authorization could not reach Google's token service."
        ) from error
    if not isinstance(payload, dict):
        raise GmailOAuthError("Google returned an invalid authorization response.")
    return payload


def _parse_token(
    payload: dict[str, Any],
    *,
    now: Callable[[], float],
    require_refresh_token: bool,
) -> GmailToken:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token", "")
    expires_in = payload.get("expires_in")
    scope = payload.get("scope", GMAIL_METADATA_SCOPE)
    if not isinstance(access_token, str) or not access_token.strip():
        raise GmailOAuthError("Google did not return an access token.")
    if require_refresh_token and (
        not isinstance(refresh_token, str) or not refresh_token.strip()
    ):
        raise GmailOAuthError("Google did not return a refresh token.")
    if not isinstance(refresh_token, str):
        raise GmailOAuthError("Google returned an invalid refresh token.")
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise GmailOAuthError("Google returned an invalid token lifetime.")
    if not isinstance(scope, str):
        raise GmailOAuthError("Google returned invalid authorization scopes.")
    scopes = tuple(sorted(set(scope.split()), key=str.casefold))
    if GMAIL_METADATA_SCOPE not in scopes:
        raise GmailOAuthError("Google did not grant Gmail metadata access.")
    return GmailToken(
        access_token=access_token.strip(),
        refresh_token=refresh_token.strip(),
        expires_at=now() + expires_in,
        scopes=scopes,
    )


def _single_query_value(
    query: dict[str, list[str]],
    name: str,
    *,
    required: bool = True,
) -> str | None:
    values = query.get(name)
    if values is None:
        if required:
            raise GmailOAuthError(f"Gmail callback is missing {name}.")
        return None
    if len(values) != 1:
        raise GmailOAuthError(f"Gmail callback contains an invalid {name}.")
    return values[0]
