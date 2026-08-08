"""Tests for bounded Spotify album search, opening, and playback."""

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
from project_akiha.integrations.spotify.albums import (
    SpotifyAlbumOpenExecutor,
    SpotifyAlbumPlaybackExecutor,
    SpotifyAlbumSearchExecutor,
    SpotifyAlbumSelectionStore,
)
from project_akiha.integrations.spotify.client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyDevice,
    SpotifyItemKind,
    SpotifySearchResult,
)
from project_akiha.integrations.spotify.devices import (
    SpotifyDeviceResolution,
    SpotifyDeviceStatus,
)


class SpotifyAlbumSearchExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()

    def test_search_returns_bounded_album_results_without_side_effects(self) -> None:
        albums = tuple(
            _album(f"album{index}", f"Album {index}", "ADO") for index in range(1, 6)
        )
        client = _AlbumClient(albums)
        executor = SpotifyAlbumSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.search_albums",
                    "Album",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["album_candidates"], albums)
        self.assertEqual(client.searches, ["album:Album artist:ADO"])
        self.assertEqual(client.played, [])

    def test_search_relaxes_filters_after_imperfect_voice_spelling(self) -> None:
        match = _album("album1", "Kyougen", "ADO")
        client = _AlbumClient(
            (),
            search_results={"Kyo gen ADO": (match,)},
        )
        executor = SpotifyAlbumSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.search_albums",
                    "Kyo gen",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.metadata["album_candidates"], (match,))
        self.assertEqual(
            client.searches,
            ["album:Kyo gen artist:ADO", "Kyo gen ADO"],
        )


class SpotifyAlbumOpenExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()

    def test_open_uses_validated_album_id_without_playback(self) -> None:
        opened: list[str] = []
        client = _AlbumClient((_album("album1", "Kyougen", "ADO"),))
        executor = SpotifyAlbumOpenExecutor(
            client,  # type: ignore[arg-type]
            opener=lambda album_id: not opened.append(album_id),
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.open_album",
                    "Kyougen",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(opened, ["album1"])
        self.assertEqual(client.played, [])
        self.assertEqual(result.metadata["album_artist"], "ADO")

    def test_ambiguous_open_returns_bounded_choices(self) -> None:
        candidates = (
            _album("album1", "Kyougen", "ADO"),
            _album("album2", "Kyougen", "ADO"),
        )
        client = _AlbumClient(candidates)
        executor = SpotifyAlbumOpenExecutor(
            client,  # type: ignore[arg-type]
            opener=lambda _album_id: True,
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.open_album",
                    "Kyougen",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(result.metadata["album_candidates"], candidates)


class SpotifyAlbumPlaybackExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()
        self.coordinator = _Coordinator(_ready(_desktop_device()))

    def test_exact_album_starts_one_context(self) -> None:
        client = _AlbumClient((_album("album1", "Kyougen", "ADO"),))
        executor = SpotifyAlbumPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.play_album",
                    "Kyougen",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(
            client.played,
            [("desktop-id", "spotify:album:album1")],
        )
        self.assertEqual(result.metadata["album_artist"], "ADO")

    def test_numbered_follow_up_plays_selected_album_without_search(self) -> None:
        selected = _album("album2", "Kyougen", "ADO")
        store = SpotifyAlbumSelectionStore()
        store.replace(
            (_album("album1", "Kyougen", "ADO"), selected),
            allowed_action_ids=("spotify.play_album", "spotify.open_album"),
        )
        request = store.parse_follow_up("Akiha, play album result two.")
        self.assertIsNotNone(request)
        client = _AlbumClient(())
        executor = SpotifyAlbumPlaybackExecutor(
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
            [("desktop-id", "spotify:album:album2")],
        )

    def test_transient_device_404_re_resolves_and_retries_once(self) -> None:
        client = _AlbumClient(
            (_album("album1", "Kyougen", "ADO"),),
            play_errors=(SpotifyAPIError("missing", status_code=404),),
        )
        executor = SpotifyAlbumPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
            retry_delay_seconds=0,
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.play_album",
                    "Kyougen",
                    "ADO",
                ),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(client.played), 2)
        self.assertEqual(self.coordinator.allow_activation, [True, False])

    def test_cancelled_request_has_no_search_or_playback(self) -> None:
        token = ActionCancellationToken()
        token.cancel()
        client = _AlbumClient((_album("album1", "Kyougen", "ADO"),))
        executor = SpotifyAlbumPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(
                    self.validator,
                    "spotify.play_album",
                    "Kyougen",
                    "ADO",
                ),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(client.searches, [])
        self.assertEqual(client.played, [])


class SpotifyAlbumSelectionStoreTest(unittest.TestCase):
    def test_search_results_allow_explicit_open_follow_up(self) -> None:
        album = _album("album1", "Kyougen", "ADO")
        store = SpotifyAlbumSelectionStore()
        store.replace(
            (album,),
            allowed_action_ids=("spotify.play_album", "spotify.open_album"),
        )

        request = store.parse_follow_up("Open album result 1")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "spotify.open_album")
        self.assertEqual(request.parameters["album_uri"], "spotify:album:album1")

    def test_stale_result_reference_reports_no_active_results(self) -> None:
        store = SpotifyAlbumSelectionStore()

        error = store.follow_up_error("Play album result 11")

        self.assertEqual(
            error,
            "There are no active Spotify album results. Search for an album first.",
        )

    def test_out_of_range_result_reports_current_bound(self) -> None:
        store = SpotifyAlbumSelectionStore()
        store.replace(
            (
                _album("album1", "Kyougen", "ADO"),
                _album("album2", "Zanmu", "ADO"),
            )
        )

        error = store.follow_up_error("Play album result 11")

        self.assertEqual(error, "Choose an album result from 1 to 2.")

    def test_last_selected_album_supports_explicit_context_follow_up(self) -> None:
        store = SpotifyAlbumSelectionStore()
        store.remember_selected("Kyougen", "spotify:album:album1", "ADO")
        store.clear_candidates()

        request = store.parse_follow_up("Play that album!")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "spotify.play_album")
        self.assertEqual(request.parameters["album_name"], "Kyougen")
        self.assertEqual(request.parameters["album_uri"], "spotify:album:album1")
        self.assertEqual(request.parameters["album_artist"], "ADO")

    def test_last_selected_album_can_be_opened_without_catalog_search(self) -> None:
        store = SpotifyAlbumSelectionStore()
        store.remember_selected("Kyougen", "spotify:album:album1", "ADO")

        request = store.parse_follow_up("Akiha, open the same album on Spotify.")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "spotify.open_album")
        self.assertEqual(request.source, "spotify_context_followup")

    def test_context_follow_up_without_selected_album_returns_safe_error(self) -> None:
        store = SpotifyAlbumSelectionStore()

        error = store.follow_up_error("Play that album")

        self.assertEqual(
            error,
            "There is no recent Spotify album to use. "
            "Search for or open an album first.",
        )

    def test_chat_reset_clears_last_selected_album(self) -> None:
        store = SpotifyAlbumSelectionStore()
        store.remember_selected("Kyougen", "spotify:album:album1", "ADO")

        store.clear()

        self.assertIsNone(store.parse_follow_up("Play that album"))

    def test_last_selected_album_rejects_invalid_uri(self) -> None:
        store = SpotifyAlbumSelectionStore()

        with self.assertRaises(ValueError):
            store.remember_selected("Kyougen", "https://example.com/album1", "ADO")


class _AlbumClient:
    def __init__(
        self,
        albums: tuple[SpotifyCatalogItem, ...],
        *,
        search_results: dict[str, tuple[SpotifyCatalogItem, ...]] | None = None,
        play_errors: tuple[SpotifyAPIError, ...] = (),
    ) -> None:
        self.albums = albums
        self.search_results = search_results or {}
        self.play_errors = list(play_errors)
        self.searches: list[str] = []
        self.played: list[tuple[str, str]] = []

    def search(
        self,
        query: str,
        *,
        kinds: tuple[SpotifyItemKind, ...],
        limit_per_kind: int,
    ) -> SpotifySearchResult:
        if kinds != (SpotifyItemKind.ALBUM,) or limit_per_kind != 5:
            raise AssertionError("Album search was not bounded correctly.")
        self.searches.append(query)
        return SpotifySearchResult(
            query=query,
            items=self.search_results.get(query, self.albums),
        )

    def start_context_playback(self, device_id: str, context_uri: str) -> None:
        self.played.append((device_id, context_uri))
        if self.play_errors:
            raise self.play_errors.pop(0)


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
    parameters = {"service": "spotify", "album_query": title}
    if artist:
        parameters["artist_query"] = artist
    return validator.validate(
        ActionRequest(
            correlation_id="spotify-album-1",
            action_id=action_id,
            source="chat",
            parameters=parameters,
        )
    )


def _album(spotify_id: str, name: str, artist: str) -> SpotifyCatalogItem:
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.ALBUM,
        spotify_id=spotify_id,
        uri=f"spotify:album:{spotify_id}",
        name=name,
        artist_names=(artist,),
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
