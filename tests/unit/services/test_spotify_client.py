"""Tests for bounded Spotify catalog and personal-library access."""

from __future__ import annotations

import unittest
from collections.abc import Mapping
from urllib.parse import parse_qs, urlparse

from project_akiha.config import SpotifyConfig
from project_akiha.services.spotify_client import (
    SPOTIFY_API_BASE_URL,
    SpotifyAPIError,
    SpotifyClient,
    SpotifyDevice,
    SpotifyItemKind,
)


class _Session:
    def __init__(self) -> None:
        self.token_number = 1
        self.clear_count = 0
        self.applied: list[SpotifyConfig] = []

    def get_access_token(self) -> str:
        return f"access-{self.token_number}"

    def clear_access_token(self) -> None:
        self.clear_count += 1
        self.token_number += 1

    def apply_config(self, config: SpotifyConfig) -> None:
        self.applied.append(config)


class _Transport:
    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.payloads = list(payloads)
        self.requests: list[tuple[str, Mapping[str, str], float]] = []

    def __call__(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> dict[str, object]:
        self.requests.append((url, headers, timeout))
        if not self.payloads:
            raise AssertionError("Unexpected Spotify request.")
        return self.payloads.pop(0)


class SpotifyClientTest(unittest.TestCase):
    """Verify Spotify responses become minimal typed local metadata."""

    def setUp(self) -> None:
        self.config = SpotifyConfig(enabled=True, client_id="a" * 32)
        self.session = _Session()

    def test_search_is_bounded_typed_and_authenticated(self) -> None:
        transport = _Transport(
            [
                {
                    "tracks": {
                        "items": [
                            _track(
                                "track-1",
                                "Night Signal",
                                "Synthetic Singer",
                                album="Signal Archive",
                            ),
                            {"id": "missing-fields"},
                        ]
                    },
                    "artists": {
                        "items": [
                            {
                                "id": "artist-1",
                                "uri": "spotify:artist:artist-1",
                                "name": "Synthetic Singer",
                                "type": "artist",
                            }
                        ]
                    },
                }
            ]
        )
        client = SpotifyClient(self.config, self.session, transport=transport)

        result = client.search(
            "  Night   Signal  ",
            kinds=(SpotifyItemKind.TRACK, SpotifyItemKind.ARTIST),
            limit_per_kind=10,
        )

        self.assertEqual(result.query, "Night Signal")
        self.assertEqual(len(result.items), 2)
        track = result.items[0]
        self.assertEqual(track.kind, SpotifyItemKind.TRACK)
        self.assertEqual(track.artist_names, ("Synthetic Singer",))
        self.assertEqual(track.album_name, "Signal Archive")
        self.assertEqual(track.display_label, "Night Signal - Synthetic Singer")
        url, headers, timeout = transport.requests[0]
        parsed = urlparse(url)
        self.assertEqual(
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            f"{SPOTIFY_API_BASE_URL}/search",
        )
        query = parse_qs(parsed.query)
        self.assertEqual(query["q"], ["Night Signal"])
        self.assertEqual(query["type"], ["track,artist"])
        self.assertEqual(query["limit"], ["10"])
        self.assertEqual(headers["Authorization"], "Bearer access-1")
        self.assertEqual(timeout, 15.0)

    def test_search_rejects_empty_oversized_or_unbounded_requests(self) -> None:
        client = SpotifyClient(self.config, self.session, transport=_Transport([]))

        for query in ("", " " * 4, "x" * 257):
            with self.subTest(query_length=len(query)):
                with self.assertRaises(ValueError):
                    client.search(query)
        with self.assertRaises(ValueError):
            client.search("test", kinds=())
        with self.assertRaises(ValueError):
            client.search("test", limit_per_kind=11)

    def test_saved_tracks_rebuilds_bounded_pagination_urls(self) -> None:
        transport = _Transport(
            [
                {
                    "items": [
                        {"track": _track("one", "First Track", "Artist One")},
                        {"track": _track("two", "Second Track", "Artist Two")},
                    ],
                    "next": "https://attacker.invalid/private",
                },
                {
                    "items": [
                        {"track": _track("three", "Third Track", "Artist Three")}
                    ],
                    "next": None,
                },
            ]
        )
        client = SpotifyClient(self.config, self.session, transport=transport)

        tracks = client.get_saved_tracks(max_items=3)

        self.assertEqual(
            [item.name for item in tracks],
            ["First Track", "Second Track", "Third Track"],
        )
        self.assertEqual(len(transport.requests), 2)
        first_query = parse_qs(urlparse(transport.requests[0][0]).query)
        second_url = urlparse(transport.requests[1][0])
        second_query = parse_qs(second_url.query)
        self.assertEqual(first_query["limit"], ["3"])
        self.assertEqual(second_url.netloc, "api.spotify.com")
        self.assertEqual(second_url.path, "/v1/me/tracks")
        self.assertEqual(second_query["offset"], ["2"])
        self.assertEqual(second_query["limit"], ["1"])

    def test_playlists_keep_only_minimal_owner_metadata(self) -> None:
        transport = _Transport(
            [
                {
                    "items": [
                        {
                            "id": "playlist-1",
                            "uri": "spotify:playlist:playlist-1",
                            "name": "Evening Mix",
                            "type": "playlist",
                            "description": "Not retained",
                            "images": [{"url": "https://images.invalid/private"}],
                            "owner": {
                                "id": "owner-id",
                                "display_name": "Local Listener",
                            },
                        }
                    ],
                    "next": None,
                }
            ]
        )
        client = SpotifyClient(self.config, self.session, transport=transport)

        playlists = client.get_playlists(max_items=5)

        self.assertEqual(len(playlists), 1)
        self.assertEqual(playlists[0].owner_name, "Local Listener")
        self.assertFalse(hasattr(playlists[0], "description"))
        self.assertFalse(hasattr(playlists[0], "images"))

    def test_top_and_recent_items_use_fixed_provider_routes(self) -> None:
        transport = _Transport(
            [
                {
                    "items": [
                        {
                            "id": "artist-1",
                            "uri": "spotify:artist:artist-1",
                            "name": "Synthetic Singer",
                            "type": "artist",
                        }
                    ]
                },
                {"items": [{"track": _track("recent-1", "Recent Track", "Artist")}]},
            ]
        )
        client = SpotifyClient(self.config, self.session, transport=transport)

        top = client.get_top_items("artist", time_range="short_term", limit=7)
        recent = client.get_recent_tracks(limit=4)

        self.assertEqual(top[0].kind, SpotifyItemKind.ARTIST)
        self.assertEqual(recent[0].name, "Recent Track")
        top_url = urlparse(transport.requests[0][0])
        recent_url = urlparse(transport.requests[1][0])
        self.assertEqual(top_url.path, "/v1/me/top/artists")
        self.assertEqual(parse_qs(top_url.query)["time_range"], ["short_term"])
        self.assertEqual(recent_url.path, "/v1/me/player/recently-played")

    def test_available_devices_keep_only_minimal_valid_metadata(self) -> None:
        transport = _Transport(
            [
                {
                    "devices": [
                        {
                            "id": "desktop-id",
                            "is_active": True,
                            "is_private_session": True,
                            "is_restricted": False,
                            "name": "Windows PC",
                            "supports_volume": True,
                            "type": "Computer",
                            "volume_percent": 42,
                        },
                        {
                            "id": None,
                            "name": "Unaddressable device",
                            "type": "Computer",
                        },
                        "invalid",
                    ]
                }
            ]
        )
        client = SpotifyClient(self.config, self.session, transport=transport)

        devices = client.get_available_devices()

        self.assertEqual(
            devices,
            (
                SpotifyDevice(
                    device_id="desktop-id",
                    name="Windows PC",
                    device_type="computer",
                    is_active=True,
                    is_restricted=False,
                    volume_percent=42,
                    supports_volume=True,
                ),
            ),
        )
        self.assertFalse(hasattr(devices[0], "is_private_session"))
        url = transport.requests[0][0]
        self.assertEqual(url, f"{SPOTIFY_API_BASE_URL}/me/player/devices")

    def test_invalid_device_collection_fails_without_echoing_content(self) -> None:
        transport = _Transport([{"devices": {"private": "do-not-echo"}}])
        client = SpotifyClient(self.config, self.session, transport=transport)

        with self.assertRaises(SpotifyAPIError) as raised:
            client.get_available_devices()

        self.assertNotIn("do-not-echo", str(raised.exception))

    def test_invalid_top_kind_time_range_and_library_bounds_fail_locally(self) -> None:
        client = SpotifyClient(self.config, self.session, transport=_Transport([]))

        with self.assertRaises(ValueError):
            client.get_top_items("playlist")
        with self.assertRaises(ValueError):
            client.get_top_items("track", time_range="forever")
        with self.assertRaises(ValueError):
            client.get_recent_tracks(limit=51)
        with self.assertRaises(ValueError):
            client.get_saved_tracks(max_items=501)

    def test_unauthorized_request_refreshes_once(self) -> None:
        requests: list[str] = []

        def transport(
            _url: str,
            headers: Mapping[str, str],
            _timeout: float,
        ) -> dict[str, object]:
            requests.append(headers["Authorization"])
            if len(requests) == 1:
                raise SpotifyAPIError("expired", status_code=401)
            return {"tracks": {"items": []}}

        client = SpotifyClient(self.config, self.session, transport=transport)

        client.search("test")

        self.assertEqual(requests, ["Bearer access-1", "Bearer access-2"])
        self.assertEqual(self.session.clear_count, 1)

    def test_non_authorization_failure_is_not_retried(self) -> None:
        attempts = 0

        def transport(
            _url: str,
            _headers: Mapping[str, str],
            _timeout: float,
        ) -> dict[str, object]:
            nonlocal attempts
            attempts += 1
            raise SpotifyAPIError("rate limited", status_code=429)

        client = SpotifyClient(self.config, self.session, transport=transport)

        with self.assertRaisesRegex(SpotifyAPIError, "rate limited"):
            client.search("test")

        self.assertEqual(attempts, 1)
        self.assertEqual(self.session.clear_count, 0)

    def test_malformed_pages_cannot_create_unbounded_pagination(self) -> None:
        transport = _Transport(
            [
                {"items": [{"track": None}], "next": "continue"},
                {"items": [{"track": None}], "next": "continue"},
            ]
        )
        client = SpotifyClient(self.config, self.session, transport=transport)

        tracks = client.get_saved_tracks(max_items=1)

        self.assertEqual(tracks, ())
        self.assertEqual(len(transport.requests), 2)

    def test_invalid_collection_fails_without_echoing_response_content(self) -> None:
        transport = _Transport([{"tracks": {"private": "do-not-echo"}}])
        client = SpotifyClient(self.config, self.session, transport=transport)

        with self.assertRaises(SpotifyAPIError) as raised:
            client.search("test")

        self.assertNotIn("do-not-echo", str(raised.exception))


def _track(
    spotify_id: str,
    name: str,
    artist: str,
    *,
    album: str = "Synthetic Album",
) -> dict[str, object]:
    return {
        "id": spotify_id,
        "uri": f"spotify:track:{spotify_id}",
        "name": name,
        "type": "track",
        "artists": [{"name": artist}],
        "album": {"name": album},
        "duration_ms": 180_000,
        "is_playable": True,
    }


if __name__ == "__main__":
    unittest.main()
