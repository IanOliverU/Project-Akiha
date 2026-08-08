"""Tests for bounded Spotify playlist search, selection, and playback."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.database import SQLiteActionRepository
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
from project_akiha.integrations.spotify.playlists import (
    SpotifyPlaylistPlaybackExecutor,
    SpotifyPlaylistSearchExecutor,
    SpotifyPlaylistSelectionStore,
)
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService


class SpotifyPlaylistSearchExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()

    def test_search_prioritizes_personal_playlists_and_deduplicates_catalog(
        self,
    ) -> None:
        personal = _playlist("personal1", "Night Drive", "Akiha User")
        catalog = _playlist("catalog1", "Night Drive Mix", "Spotify")
        client = _PlaylistClient(
            library=(personal,),
            catalog=(personal, catalog),
        )
        executor = SpotifyPlaylistSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.search_playlists", "Night Drive"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["playlist_candidates"], (personal, catalog))
        self.assertEqual(client.library_limits, [200])
        self.assertEqual(client.searches, ["Night Drive"])
        self.assertEqual(client.played, [])

    def test_search_keeps_only_five_valid_playlists(self) -> None:
        catalog = tuple(
            _playlist(f"playlist{index}", f"Focus {index}", "Spotify")
            for index in range(1, 8)
        )
        client = _PlaylistClient(catalog=catalog)
        executor = SpotifyPlaylistSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.search_playlists", "Focus"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(len(result.metadata["playlist_candidates"]), 5)


class SpotifyPlaylistPlaybackExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = _validator()
        self.coordinator = _Coordinator(_ready(_desktop_device()))

    def test_exact_personal_playlist_starts_validated_context(self) -> None:
        playlist = _playlist("personal1", "Night Drive", "Akiha User")
        client = _PlaylistClient(library=(playlist,), catalog=(playlist,))
        executor = SpotifyPlaylistPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.play_playlist", "Night Drive"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(
            client.played,
            [("desktop-id", "spotify:playlist:personal1")],
        )
        self.assertEqual(result.metadata["playlist_owner"], "Akiha User")

    def test_ambiguous_playlist_returns_bounded_choices(self) -> None:
        candidates = (
            _playlist("playlist1", "Focus", "Owner One"),
            _playlist("playlist2", "Focus", "Owner Two"),
        )
        client = _PlaylistClient(catalog=candidates)
        executor = SpotifyPlaylistPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.play_playlist", "Focus"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(result.metadata["playlist_candidates"], candidates)
        self.assertEqual(client.played, [])

    def test_numbered_follow_up_plays_without_library_or_catalog_search(self) -> None:
        selected = _playlist("playlist2", "Focus", "Owner Two")
        store = SpotifyPlaylistSelectionStore()
        store.replace((_playlist("playlist1", "Focus", "Owner One"), selected))
        request = store.parse_follow_up("Play playlist result two")
        self.assertIsNotNone(request)
        client = _PlaylistClient()
        executor = SpotifyPlaylistPlaybackExecutor(
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
        self.assertEqual(client.library_limits, [])
        self.assertEqual(client.searches, [])
        self.assertEqual(
            client.played,
            [("desktop-id", "spotify:playlist:playlist2")],
        )

    def test_transient_device_404_re_resolves_and_retries_once(self) -> None:
        playlist = _playlist("playlist1", "Focus", "Owner")
        client = _PlaylistClient(
            library=(playlist,),
            play_errors=(SpotifyAPIError("missing", status_code=404),),
        )
        executor = SpotifyPlaylistPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
            retry_delay_seconds=0,
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.play_playlist", "Focus"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(client.played), 2)
        self.assertEqual(self.coordinator.allow_activation, [True, False])

    def test_cancelled_request_has_no_library_search_or_playback(self) -> None:
        token = ActionCancellationToken()
        token.cancel()
        client = _PlaylistClient()
        executor = SpotifyPlaylistPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "spotify.play_playlist", "Focus"),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(client.library_limits, [])
        self.assertEqual(client.searches, [])
        self.assertEqual(client.played, [])

    def test_playlist_playback_uses_existing_permission_and_is_audited(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            path_policy = ProtectedPathPolicy()
            client = _PlaylistClient()
            executor = SpotifyPlaylistPlaybackExecutor(
                client,  # type: ignore[arg-type]
                self.coordinator,  # type: ignore[arg-type]
            )
            service = AssistantActionService(
                ActionRequestValidator(build_default_action_registry(), path_policy),
                ActionPermissionPolicy(path_policy),
                repository,
                repository,
                executors=(executor,),
            )
            permissions = AssistantPermissionService(repository, path_policy)
            asyncio.run(permissions.grant_spotify_playback())
            request = ActionRequest(
                correlation_id="spotify-playlist-audit",
                action_id="spotify.play_playlist",
                source="voice",
                parameters={
                    "service": "spotify",
                    "playlist_query": "Night Drive",
                    "playlist_name": "Night Drive",
                    "playlist_uri": "spotify:playlist:personal1",
                    "playlist_owner": "Akiha User",
                },
            )

            result = asyncio.run(service.evaluate_request(request))
            audits = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(
            client.played,
            [("desktop-id", "spotify:playlist:personal1")],
        )
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action_id, "spotify.play_playlist")
        self.assertEqual(audits[0].normalized_target, "spotify")


class SpotifyPlaylistSelectionStoreTest(unittest.TestCase):
    def test_context_follow_up_reuses_only_validated_last_playlist(self) -> None:
        store = SpotifyPlaylistSelectionStore()
        store.remember_selected(
            "Night Drive",
            "spotify:playlist:personal1",
            "Akiha User",
        )

        request = store.parse_follow_up("Play that playlist on Spotify")

        self.assertIsNotNone(request)
        self.assertEqual(request.action_id, "spotify.play_playlist")
        self.assertEqual(
            request.parameters["playlist_uri"], "spotify:playlist:personal1"
        )

    def test_stale_and_out_of_range_results_return_safe_feedback(self) -> None:
        store = SpotifyPlaylistSelectionStore()
        self.assertEqual(
            store.follow_up_error("Play playlist result 4"),
            "There are no active Spotify playlist results. "
            "Search for a playlist first.",
        )
        store.replace((_playlist("playlist1", "Focus", "Owner"),))
        self.assertEqual(
            store.follow_up_error("Play playlist result 4"),
            "Choose a playlist result from 1 to 1.",
        )

    def test_chat_reset_clears_last_selected_playlist(self) -> None:
        store = SpotifyPlaylistSelectionStore()
        store.remember_selected("Focus", "spotify:playlist:playlist1", "Owner")

        store.clear()

        self.assertIsNone(store.parse_follow_up("Play that playlist"))

    def test_invalid_selected_playlist_uri_is_rejected(self) -> None:
        store = SpotifyPlaylistSelectionStore()

        with self.assertRaises(ValueError):
            store.remember_selected("Focus", "https://example.com/playlist", "Owner")


class _PlaylistClient:
    def __init__(
        self,
        *,
        library: tuple[SpotifyCatalogItem, ...] = (),
        catalog: tuple[SpotifyCatalogItem, ...] = (),
        play_errors: tuple[SpotifyAPIError, ...] = (),
    ) -> None:
        self.library = library
        self.catalog = catalog
        self.play_errors = list(play_errors)
        self.library_limits: list[int] = []
        self.searches: list[str] = []
        self.played: list[tuple[str, str]] = []

    def get_playlists(self, *, max_items: int) -> tuple[SpotifyCatalogItem, ...]:
        self.library_limits.append(max_items)
        return self.library

    def search(
        self,
        query: str,
        *,
        kinds: tuple[SpotifyItemKind, ...],
        limit_per_kind: int,
    ) -> SpotifySearchResult:
        if kinds != (SpotifyItemKind.PLAYLIST,) or limit_per_kind != 5:
            raise AssertionError("Playlist search was not bounded correctly.")
        self.searches.append(query)
        return SpotifySearchResult(query=query, items=self.catalog)

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
        build_default_action_registry(),
        ProtectedPathPolicy(),
    )


def _validated(
    validator: ActionRequestValidator,
    action_id: str,
    query: str,
):
    return validator.validate(
        ActionRequest(
            correlation_id="spotify-playlist-1",
            action_id=action_id,
            source="chat",
            parameters={"service": "spotify", "playlist_query": query},
        )
    )


def _playlist(spotify_id: str, name: str, owner: str) -> SpotifyCatalogItem:
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.PLAYLIST,
        spotify_id=spotify_id,
        uri=f"spotify:playlist:{spotify_id}",
        name=name,
        owner_name=owner,
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
