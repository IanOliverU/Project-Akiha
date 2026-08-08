"""Tests for Spotify PKCE authorization primitives."""

from __future__ import annotations

import unittest
from urllib.parse import parse_qs, parse_qsl, urlparse

from project_akiha.config import SpotifyConfig
from project_akiha.integrations.spotify.auth import (
    SPOTIFY_SCOPES,
    SpotifyOAuthError,
    create_spotify_authorization_session,
    exchange_spotify_authorization_code,
    parse_spotify_callback,
    refresh_spotify_access_token,
)


class SpotifyAuthTest(unittest.TestCase):
    """Verify Spotify auth is PKCE-only and callback state is mandatory."""

    def setUp(self) -> None:
        self.config = SpotifyConfig(enabled=True, client_id="a" * 32)

    def test_authorization_url_uses_pkce_and_expected_scopes(self) -> None:
        session = create_spotify_authorization_session(
            self.config,
            code_verifier="v" * 64,
            state="expected-state",
        )

        parsed = urlparse(session.authorization_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "accounts.spotify.com")
        self.assertEqual(query["client_id"], ["a" * 32])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", query)
        self.assertEqual(set(query["scope"][0].split()), set(SPOTIFY_SCOPES))

    def test_pkce_verifier_rejects_non_ascii_or_unsafe_characters(self) -> None:
        for verifier in ("v" * 42, "v" * 129, "é" * 64, "v" * 63 + " "):
            with self.subTest(verifier=verifier):
                with self.assertRaises(SpotifyOAuthError):
                    create_spotify_authorization_session(
                        self.config,
                        code_verifier=verifier,
                        state="expected-state",
                    )

    def test_callback_requires_matching_single_state(self) -> None:
        with self.assertRaises(SpotifyOAuthError):
            parse_spotify_callback(
                "/callback?code=test&state=wrong",
                expected_state="expected",
                redirect_uri=self.config.redirect_uri,
            )

        with self.assertRaises(SpotifyOAuthError):
            parse_spotify_callback(
                "/callback?code=test&state=expected&state=duplicate",
                expected_state="expected",
                redirect_uri=self.config.redirect_uri,
            )

    def test_cancelled_callback_returns_privacy_safe_error(self) -> None:
        with self.assertRaisesRegex(SpotifyOAuthError, "cancelled"):
            parse_spotify_callback(
                "/callback?error=access_denied&state=expected",
                expected_state="expected",
                redirect_uri=self.config.redirect_uri,
            )

    def test_code_exchange_never_sends_client_secret(self) -> None:
        session = create_spotify_authorization_session(
            self.config,
            code_verifier="v" * 64,
            state="expected",
        )
        code = parse_spotify_callback(
            "/callback?code=returned-code&state=expected",
            expected_state="expected",
            redirect_uri=self.config.redirect_uri,
        )
        captured: dict[str, str] = {}

        def transport(_url: str, data: bytes, _timeout: float) -> dict[str, object]:
            captured.update(parse_qsl(data.decode("ascii")))
            return {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
                "scope": "user-library-read user-modify-playback-state",
            }

        token = exchange_spotify_authorization_code(
            session,
            code,
            timeout_seconds=15,
            transport=transport,
            now=lambda: 100.0,
        )

        self.assertEqual(token.access_token, "access")
        self.assertEqual(token.refresh_token, "refresh")
        self.assertEqual(token.expires_at, 3700.0)
        self.assertEqual(captured["code_verifier"], "v" * 64)
        self.assertNotIn("client_secret", captured)

    def test_refresh_preserves_existing_refresh_token(self) -> None:
        def transport(_url: str, data: bytes, _timeout: float) -> dict[str, object]:
            request = dict(parse_qsl(data.decode("ascii")))
            self.assertEqual(request["refresh_token"], "saved-refresh")
            return {
                "access_token": "new-access",
                "expires_in": 1800,
                "scope": "user-library-read",
            }

        token = refresh_spotify_access_token(
            self.config,
            "saved-refresh",
            transport=transport,
            now=lambda: 50.0,
        )

        self.assertEqual(token.refresh_token, "saved-refresh")
        self.assertEqual(token.expires_at, 1850.0)


if __name__ == "__main__":
    unittest.main()
