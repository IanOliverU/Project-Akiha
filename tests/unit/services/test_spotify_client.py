"""Tests for bounded Spotify catalog and personal-library access."""

from __future__ import annotations

import json
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


class _MutationTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, Mapping[str, str], bytes | None, float]] = (
            []
        )

    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: float,
    ) -> None:
        self.requests.append((method, url, headers, body, timeout))


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

    def test_multi_track_playback_accepts_only_a_bounded_unique_uri_queue(
        self,
    ) -> None:
        mutation = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            transport=_Transport([]),
            mutation_transport=mutation,
        )

        client.start_tracks_playback(
            "desktop-id",
            ("spotify:track:one", "spotify:track:two"),
        )

        method, url, _headers, body, _timeout = mutation.requests[0]
        self.assertEqual(method, "PUT")
        self.assertEqual(urlparse(url).path, "/v1/me/player/play")
        self.assertEqual(
            json.loads((body or b"").decode("utf-8")),
            {"uris": ["spotify:track:one", "spotify:track:two"]},
        )
        for invalid in (
            (),
            ("not-a-track",),
            ("spotify:track:one", "spotify:track:one"),
            tuple(f"spotify:track:{index}" for index in range(51)),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    client.start_tracks_playback("desktop-id", invalid)

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

    def test_playback_controls_use_only_fixed_player_routes(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            transport=_Transport([]),
            mutation_transport=mutations,
        )

        client.start_or_resume_playback(" desktop-id ")
        client.start_context_playback(
            "desktop-id",
            "spotify:artist:artist1",
        )
        client.start_track_playback("desktop-id", "spotify:track:track1")
        client.pause_playback("desktop-id")
        client.skip_to_next("desktop-id")
        client.skip_to_previous("desktop-id")
        client.set_shuffle("desktop-id", True)
        client.set_shuffle("desktop-id", False)
        client.set_repeat("desktop-id", "track")
        client.set_repeat("desktop-id", "context")
        client.set_repeat("desktop-id", "off")
        client.set_volume("desktop-id", 42)
        client.seek_playback("desktop-id", 90_000)

        self.assertEqual(
            [(method, urlparse(url).path) for method, url, *_ in mutations.requests],
            [
                ("PUT", "/v1/me/player/play"),
                ("PUT", "/v1/me/player/play"),
                ("PUT", "/v1/me/player/play"),
                ("PUT", "/v1/me/player/pause"),
                ("POST", "/v1/me/player/next"),
                ("POST", "/v1/me/player/previous"),
                ("PUT", "/v1/me/player/shuffle"),
                ("PUT", "/v1/me/player/shuffle"),
                ("PUT", "/v1/me/player/repeat"),
                ("PUT", "/v1/me/player/repeat"),
                ("PUT", "/v1/me/player/repeat"),
                ("PUT", "/v1/me/player/volume"),
                ("PUT", "/v1/me/player/seek"),
            ],
        )
        for index, (_method, url, headers, _body, timeout) in enumerate(
            mutations.requests
        ):
            expected_query = {"device_id": ["desktop-id"]}
            if index == 6:
                expected_query["state"] = ["true"]
            elif index == 7:
                expected_query["state"] = ["false"]
            elif index == 8:
                expected_query["state"] = ["track"]
            elif index == 9:
                expected_query["state"] = ["context"]
            elif index == 10:
                expected_query["state"] = ["off"]
            elif index == 11:
                expected_query["volume_percent"] = ["42"]
            elif index == 12:
                expected_query["position_ms"] = ["90000"]
            self.assertEqual(
                parse_qs(urlparse(url).query),
                expected_query,
            )
            self.assertEqual(headers["Authorization"], "Bearer access-1")
            self.assertEqual(timeout, 15.0)
        self.assertEqual(mutations.requests[0][3], b"{}")
        self.assertEqual(
            mutations.requests[1][3],
            b'{"context_uri":"spotify:artist:artist1"}',
        )
        self.assertEqual(
            mutations.requests[2][3],
            b'{"uris":["spotify:track:track1"]}',
        )
        self.assertEqual(mutations.requests[3][3], None)

    def test_shuffle_rejects_non_boolean_state_without_request(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        with self.assertRaises(ValueError):
            client.set_shuffle("desktop-id", 1)  # type: ignore[arg-type]

        self.assertEqual(mutations.requests, [])

    def test_repeat_rejects_unallowlisted_mode_without_request(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        for mode in ("", "all", "forever"):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    client.set_repeat("desktop-id", mode)

        self.assertEqual(mutations.requests, [])

    def test_volume_rejects_out_of_range_values_without_request(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        for volume_percent in (-1, 101, True):
            with self.subTest(volume_percent=volume_percent):
                with self.assertRaises(ValueError):
                    client.set_volume(
                        "desktop-id",
                        volume_percent,  # type: ignore[arg-type]
                    )

        self.assertEqual(mutations.requests, [])

    def test_seek_rejects_out_of_range_values_without_request(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        for position_ms in (-1, 86_400_001, False):
            with self.subTest(position_ms=position_ms):
                with self.assertRaises(ValueError):
                    client.seek_playback(
                        "desktop-id",
                        position_ms,  # type: ignore[arg-type]
                    )

        self.assertEqual(mutations.requests, [])

    def test_context_playback_rejects_untrusted_or_unsupported_uri(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        for context_uri in (
            "",
            "https://open.spotify.com/artist/artist1",
            "spotify:track:track1",
            "spotify:artist:bad/value",
        ):
            with self.subTest(context_uri=context_uri):
                with self.assertRaises(ValueError):
                    client.start_context_playback("desktop-id", context_uri)

        self.assertEqual(mutations.requests, [])

    def test_track_playback_rejects_untrusted_or_non_track_uri(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        for track_uri in (
            "",
            "https://open.spotify.com/track/track1",
            "spotify:artist:artist1",
            "spotify:track:bad/value",
        ):
            with self.subTest(track_uri=track_uri):
                with self.assertRaises(ValueError):
                    client.start_track_playback("desktop-id", track_uri)

        self.assertEqual(mutations.requests, [])

    def test_playback_rejects_invalid_device_id_before_network(self) -> None:
        mutations = _MutationTransport()
        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutations,
        )

        for device_id in ("", " ", "bad\nidentifier", "x" * 257):
            with self.subTest(device_id=device_id):
                with self.assertRaises(ValueError):
                    client.pause_playback(device_id)

        self.assertEqual(mutations.requests, [])

    def test_playback_unauthorized_request_refreshes_once(self) -> None:
        requests: list[str] = []

        def mutation_transport(
            _method: str,
            _url: str,
            headers: Mapping[str, str],
            _body: bytes | None,
            _timeout: float,
        ) -> None:
            requests.append(headers["Authorization"])
            if len(requests) == 1:
                raise SpotifyAPIError("expired", status_code=401)

        client = SpotifyClient(
            self.config,
            self.session,
            mutation_transport=mutation_transport,
        )

        client.skip_to_next("desktop-id")

        self.assertEqual(requests, ["Bearer access-1", "Bearer access-2"])
        self.assertEqual(self.session.clear_count, 1)

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
