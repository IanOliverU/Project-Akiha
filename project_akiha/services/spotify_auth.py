"""Spotify OAuth 2.0 Authorization Code with PKCE primitives."""

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

from project_akiha.config import SpotifyConfig

SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_SCOPES = (
    "playlist-read-private",
    "user-library-read",
    "user-modify-playback-state",
    "user-read-playback-state",
    "user-read-recently-played",
    "user-top-read",
)

TokenTransport = Callable[[str, bytes, float], dict[str, Any]]
_PKCE_VERIFIER_PATTERN = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z")


class SpotifyOAuthError(RuntimeError):
    """Raised when Spotify authorization cannot complete safely."""


@dataclass(frozen=True, slots=True)
class SpotifyAuthorizationSession:
    """Short-lived PKCE values required for one browser authorization."""

    authorization_url: str
    client_id: str
    redirect_uri: str
    state: str
    code_verifier: str


@dataclass(frozen=True, slots=True)
class SpotifyAuthorizationCode:
    """Validated code returned to Akiha's loopback callback."""

    code: str


@dataclass(frozen=True, slots=True)
class SpotifyToken:
    """Spotify access token plus the refresh token kept by secure storage."""

    access_token: str
    refresh_token: str
    expires_at: float
    scopes: tuple[str, ...]


def create_spotify_authorization_session(
    config: SpotifyConfig,
    *,
    code_verifier: str | None = None,
    state: str | None = None,
) -> SpotifyAuthorizationSession:
    """Create a PKCE authorization URL without using a client secret."""
    if not config.enabled:
        raise SpotifyOAuthError("Spotify integration is disabled.")
    verifier = code_verifier or secrets.token_urlsafe(64)
    if _PKCE_VERIFIER_PATTERN.fullmatch(verifier) is None:
        raise SpotifyOAuthError("The Spotify PKCE verifier has an invalid format.")
    state_token = state or secrets.token_urlsafe(32)
    if not state_token:
        raise SpotifyOAuthError("The Spotify authorization state is empty.")
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
            "scope": " ".join(SPOTIFY_SCOPES),
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state_token,
        }
    )
    return SpotifyAuthorizationSession(
        authorization_url=f"{SPOTIFY_AUTHORIZE_URL}?{query}",
        client_id=config.client_id.strip(),
        redirect_uri=config.redirect_uri,
        state=state_token,
        code_verifier=verifier,
    )


def parse_spotify_callback(
    request_target: str,
    *,
    expected_state: str,
    redirect_uri: str,
) -> SpotifyAuthorizationCode:
    """Validate callback path, CSRF state, and returned authorization code."""
    expected = urlparse(redirect_uri)
    callback = urlparse(request_target)
    if callback.path != expected.path:
        raise SpotifyOAuthError("Spotify returned to an unexpected callback path.")
    query = parse_qs(callback.query, keep_blank_values=True)
    if _single_query_value(query, "state") != expected_state:
        raise SpotifyOAuthError("Spotify authorization state validation failed.")
    provider_error = _single_query_value(query, "error", required=False)
    if provider_error is not None:
        if provider_error == "access_denied":
            raise SpotifyOAuthError("Spotify authorization was cancelled.")
        raise SpotifyOAuthError("Spotify declined the authorization request.")
    code = _single_query_value(query, "code")
    if not code:
        raise SpotifyOAuthError("Spotify did not return an authorization code.")
    return SpotifyAuthorizationCode(code=code)


def exchange_spotify_authorization_code(
    session: SpotifyAuthorizationSession,
    code: SpotifyAuthorizationCode,
    *,
    timeout_seconds: float,
    transport: TokenTransport | None = None,
    now: Callable[[], float] = time.time,
) -> SpotifyToken:
    """Exchange a validated PKCE code for Spotify tokens."""
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


def refresh_spotify_access_token(
    config: SpotifyConfig,
    refresh_token: str,
    *,
    transport: TokenTransport | None = None,
    now: Callable[[], float] = time.time,
) -> SpotifyToken:
    """Refresh an access token while preserving a rotated or existing refresh token."""
    normalized_refresh_token = refresh_token.strip()
    if not normalized_refresh_token:
        raise SpotifyOAuthError("The saved Spotify authorization is empty.")
    payload = _exchange_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": normalized_refresh_token,
            "client_id": config.client_id.strip(),
        },
        timeout_seconds=config.request_timeout_seconds,
        transport=transport,
    )
    parsed = _parse_token(payload, now=now, require_refresh_token=False)
    return SpotifyToken(
        access_token=parsed.access_token,
        refresh_token=parsed.refresh_token or normalized_refresh_token,
        expires_at=parsed.expires_at,
        scopes=parsed.scopes,
    )


def _exchange_token(
    fields: dict[str, str],
    *,
    timeout_seconds: float,
    transport: TokenTransport | None,
) -> dict[str, Any]:
    encoded = urlencode(fields).encode("ascii")
    return (transport or _post_token)(
        SPOTIFY_TOKEN_URL,
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
            detail = "Spotify rejected the authorization. Please connect again."
        elif error.code == 429:
            detail = "Spotify temporarily rate-limited the authorization request."
        else:
            detail = f"Spotify authorization returned HTTP {error.code}."
        raise SpotifyOAuthError(detail) from error
    except (OSError, URLError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SpotifyOAuthError(
            "Spotify authorization could not reach the token service."
        ) from error
    if not isinstance(payload, dict):
        raise SpotifyOAuthError("Spotify returned an invalid authorization response.")
    return payload


def _parse_token(
    payload: dict[str, Any],
    *,
    now: Callable[[], float],
    require_refresh_token: bool,
) -> SpotifyToken:
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token", "")
    expires_in = payload.get("expires_in")
    scope = payload.get("scope", "")
    if not isinstance(access_token, str) or not access_token.strip():
        raise SpotifyOAuthError("Spotify did not return an access token.")
    if require_refresh_token and (
        not isinstance(refresh_token, str) or not refresh_token.strip()
    ):
        raise SpotifyOAuthError("Spotify did not return a refresh token.")
    if not isinstance(refresh_token, str):
        raise SpotifyOAuthError("Spotify returned an invalid refresh token.")
    if not isinstance(expires_in, int) or expires_in <= 0:
        raise SpotifyOAuthError("Spotify returned an invalid token lifetime.")
    if not isinstance(scope, str):
        raise SpotifyOAuthError("Spotify returned invalid authorization scopes.")
    return SpotifyToken(
        access_token=access_token.strip(),
        refresh_token=refresh_token.strip(),
        expires_at=now() + expires_in,
        scopes=tuple(sorted(set(scope.split()), key=str.casefold)),
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
            raise SpotifyOAuthError(f"Spotify callback is missing {name}.")
        return None
    if len(values) != 1:
        raise SpotifyOAuthError(f"Spotify callback contains an invalid {name}.")
    return values[0]
