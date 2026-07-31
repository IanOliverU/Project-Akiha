"""Tests for Spotify's encrypted-refresh and memory-access token boundary."""

from __future__ import annotations

import unittest

from project_akiha.config import SpotifyConfig
from project_akiha.services.spotify_auth import SpotifyOAuthError, SpotifyToken
from project_akiha.services.spotify_session import SpotifySession


class _SecretStore:
    def __init__(self, refresh_token: str | None = None) -> None:
        self.values: dict[tuple[str, str], str] = {}
        if refresh_token is not None:
            self.values[("spotify", "refresh_token")] = refresh_token

    def get_named_secret(self, namespace: str, name: str) -> str | None:
        return self.values.get((namespace, name))

    def set_named_secret(self, namespace: str, name: str, secret: str) -> None:
        self.values[(namespace, name)] = secret

    def delete_named_secret(self, namespace: str, name: str) -> None:
        self.values.pop((namespace, name), None)


class SpotifySessionTest(unittest.TestCase):
    """Verify access tokens are cached only in memory and refresh safely."""

    def setUp(self) -> None:
        self.config = SpotifyConfig(enabled=True, client_id="a" * 32)

    def test_refreshes_once_then_uses_memory_cache(self) -> None:
        store = _SecretStore("refresh-one")
        refreshes: list[str] = []

        def refresh(_config: SpotifyConfig, refresh_token: str) -> SpotifyToken:
            refreshes.append(refresh_token)
            return SpotifyToken("access-one", refresh_token, 200.0, ())

        session = SpotifySession(
            self.config,
            store,
            token_refresher=refresh,
            now=lambda: 100.0,
        )

        self.assertEqual(session.get_access_token(), "access-one")
        self.assertEqual(session.get_access_token(), "access-one")
        self.assertEqual(refreshes, ["refresh-one"])
        self.assertNotIn("access-one", store.values.values())

    def test_saves_rotated_refresh_token(self) -> None:
        store = _SecretStore("refresh-one")
        session = SpotifySession(
            self.config,
            store,
            token_refresher=lambda _config, _refresh: SpotifyToken(
                "access",
                "refresh-two",
                200.0,
                (),
            ),
            now=lambda: 100.0,
        )

        session.get_access_token()

        self.assertEqual(
            store.values[("spotify", "refresh_token")],
            "refresh-two",
        )

    def test_missing_connection_fails_without_refresh(self) -> None:
        session = SpotifySession(self.config, _SecretStore())

        with self.assertRaisesRegex(SpotifyOAuthError, "not connected"):
            session.get_access_token()

    def test_disabled_config_discards_cached_access_token(self) -> None:
        store = _SecretStore("refresh")
        session = SpotifySession(
            self.config,
            store,
            token_refresher=lambda _config, token: SpotifyToken(
                "access",
                token,
                200.0,
                (),
            ),
            now=lambda: 100.0,
        )
        session.get_access_token()
        session.apply_config(SpotifyConfig())

        with self.assertRaisesRegex(SpotifyOAuthError, "disabled"):
            session.get_access_token()

    def test_disconnect_removes_refresh_and_memory_token(self) -> None:
        store = _SecretStore("refresh")
        session = SpotifySession(self.config, store)

        session.disconnect()

        self.assertFalse(session.is_connected)


if __name__ == "__main__":
    unittest.main()
