"""Tests for bounded Spotify track search and playback actions."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.services.spotify_client import (
    SpotifyCatalogItem,
    SpotifyDevice,
    SpotifyItemKind,
    SpotifySearchResult,
)
from project_akiha.services.spotify_devices import (
    SpotifyDeviceResolution,
    SpotifyDeviceStatus,
)
from project_akiha.services.spotify_tracks import (
    SpotifyTrackPlaybackExecutor,
    SpotifyTrackSearchExecutor,
    SpotifyTrackSelectionStore,
)


class SpotifyTrackSearchExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()

    def test_search_returns_only_bounded_playable_tracks(self) -> None:
        playable = tuple(
            _track(f"track{index}", f"Song {index}", "Synthetic Singer")
            for index in range(1, 6)
        )
        client = _TrackClient(
            (*playable, _track("blocked1", "Blocked", "Singer", playable=False))
        )
        executor = SpotifyTrackSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.search_tracks", "Song"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["track_candidates"], playable)
        self.assertEqual(client.searches, ["track:Song"])
        self.assertEqual(client.played, [])

    def test_search_includes_artist_filter_without_exposing_results(self) -> None:
        client = _TrackClient((_track("track1", "Usseewa", "ADO"),))
        executor = SpotifyTrackSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.search_tracks",
                    "Usseewa",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(client.searches, ["track:Usseewa artist:ADO"])


class SpotifyTrackPlaybackExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()
        self.coordinator = _Coordinator(_ready(_desktop_device()))

    def test_exact_title_and_artist_play_one_track(self) -> None:
        client = _TrackClient(
            (
                _track("track1", "Usseewa", "ADO"),
                _track("track2", "Usseewa", "Tribute Singer"),
            )
        )
        executor = SpotifyTrackPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.play_track",
                    "Usseewa",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(
            client.played,
            [("desktop-id", "spotify:track:track1")],
        )
        self.assertEqual(self.coordinator.allow_activation, [True])

    def test_duplicate_exact_versions_require_a_choice(self) -> None:
        candidates = (
            _track("track1", "Usseewa", "ADO", album="Single"),
            _track("track2", "Usseewa", "ADO", album="Live"),
        )
        client = _TrackClient(candidates)
        executor = SpotifyTrackPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.play_track",
                    "Usseewa",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(result.metadata["track_candidates"], candidates)
        self.assertEqual(client.played, [])
        self.assertEqual(self.coordinator.allow_activation, [])

    def test_numbered_follow_up_plays_selected_uri_without_search(self) -> None:
        selected = _track("track2", "Usseewa", "ADO", album="Live")
        store = SpotifyTrackSelectionStore()
        store.replace((_track("track1", "Usseewa", "ADO"), selected))
        request = store.parse_follow_up("Akiha, play track result two.")
        self.assertIsNotNone(request)
        client = _TrackClient(())
        executor = SpotifyTrackPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                self.validator.validate(request),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(client.searches, [])
        self.assertEqual(
            client.played,
            [("desktop-id", "spotify:track:track2")],
        )

    def test_cancelled_request_never_searches_or_selects_device(self) -> None:
        token = ActionCancellationToken()
        token.cancel()
        client = _TrackClient((_track("track1", "Usseewa", "ADO"),))
        executor = SpotifyTrackPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.play_track", "Usseewa"),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(client.searches, [])
        self.assertEqual(self.coordinator.allow_activation, [])


class _TrackClient:
    def __init__(self, tracks: tuple[SpotifyCatalogItem, ...]) -> None:
        self.tracks = tracks
        self.searches: list[str] = []
        self.played: list[tuple[str, str]] = []

    def search(
        self,
        query: str,
        *,
        kinds: tuple[SpotifyItemKind, ...],
        limit_per_kind: int,
    ) -> SpotifySearchResult:
        if kinds != (SpotifyItemKind.TRACK,) or limit_per_kind != 5:
            raise AssertionError("Track search was not bounded correctly.")
        self.searches.append(query)
        return SpotifySearchResult(query=query, items=self.tracks)

    def start_track_playback(self, device_id: str, track_uri: str) -> None:
        self.played.append((device_id, track_uri))


class _Coordinator:
    def __init__(self, resolution: SpotifyDeviceResolution) -> None:
        self.resolution = resolution
        self.allow_activation: list[bool] = []

    async def resolve(
        self,
        _correlation_id: str,
        *,
        cancellation_token: ActionCancellationToken | None = None,
        allow_activation: bool = True,
    ) -> SpotifyDeviceResolution:
        del cancellation_token
        self.allow_activation.append(allow_activation)
        return self.resolution


def _validator() -> ActionRequestValidator:
    return ActionRequestValidator(
        build_default_action_registry(), ProtectedPathPolicy()
    )


def _validated(
    validator: ActionRequestValidator,
    action_id: str,
    title: str,
    artist: str = "",
):
    parameters = {"service": "spotify", "track_query": title}
    if artist:
        parameters["artist_query"] = artist
    return validator.validate(
        ActionRequest(
            correlation_id="spotify-track-1",
            action_id=action_id,
            source="chat",
            parameters=parameters,
        )
    )


def _track(
    spotify_id: str,
    name: str,
    artist: str,
    *,
    album: str = "Synthetic Album",
    playable: bool = True,
) -> SpotifyCatalogItem:
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.TRACK,
        spotify_id=spotify_id,
        uri=f"spotify:track:{spotify_id}",
        name=name,
        artist_names=(artist,),
        album_name=album,
        is_playable=playable,
    )


def _ready(device: SpotifyDevice) -> SpotifyDeviceResolution:
    return SpotifyDeviceResolution(
        status=SpotifyDeviceStatus.READY,
        selected_device=device,
        candidate_count=1,
    )


def _desktop_device() -> SpotifyDevice:
    return SpotifyDevice(
        device_id="desktop-id",
        name="Windows PC",
        device_type="computer",
        is_active=True,
        is_restricted=False,
    )


if __name__ == "__main__":
    unittest.main()
