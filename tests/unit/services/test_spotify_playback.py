"""Tests for typed Spotify playback action executors."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    ActionValidationError,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.database import SQLiteActionRepository
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService
from project_akiha.services.spotify_client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyDevice,
    SpotifyItemKind,
    SpotifySearchResult,
)
from project_akiha.services.spotify_devices import (
    SpotifyDeviceResolution,
    SpotifyDeviceStatus,
)
from project_akiha.services.spotify_playback import (
    SpotifyArtistOpenExecutor,
    SpotifyArtistPlaybackExecutor,
    SpotifyArtistSearchExecutor,
    SpotifyArtistSelectionStore,
    SpotifyPlaybackCommand,
    SpotifyPlaybackExecutor,
    SpotifyRepeatExecutor,
    SpotifyShuffleExecutor,
    SpotifyVolumeExecutor,
    _open_spotify_artist_page,
)


class SpotifyPlaybackExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )
        self.device = SpotifyDevice(
            device_id="desktop-id",
            name="Windows PC",
            device_type="computer",
            is_active=True,
            is_restricted=False,
        )

    def test_each_command_calls_only_its_fixed_client_method(self) -> None:
        cases = (
            (SpotifyPlaybackCommand.PLAY, "play"),
            (SpotifyPlaybackCommand.PAUSE, "pause"),
            (SpotifyPlaybackCommand.RESUME, "play"),
            (SpotifyPlaybackCommand.NEXT, "next"),
            (SpotifyPlaybackCommand.PREVIOUS, "previous"),
        )

        for command, expected_call in cases:
            with self.subTest(command=command):
                client = _PlaybackClient()
                coordinator = _Coordinator(_ready(self.device))
                executor = SpotifyPlaybackExecutor(
                    command,
                    client,  # type: ignore[arg-type]
                    coordinator,  # type: ignore[arg-type]
                )

                result = asyncio.run(
                    executor.execute(
                        self._validated(executor.action_id),
                        cancellation_token=ActionCancellationToken(),
                    )
                )

                self.assertEqual(result.status, ActionStatus.SUCCESS)
                self.assertEqual(client.calls, [(expected_call, "desktop-id")])
                self.assertEqual(
                    coordinator.allow_activation,
                    [
                        command
                        in {
                            SpotifyPlaybackCommand.PLAY,
                            SpotifyPlaybackCommand.RESUME,
                        }
                    ],
                )

    def test_missing_device_fails_without_api_mutation(self) -> None:
        client = _PlaybackClient()
        coordinator = _Coordinator(
            SpotifyDeviceResolution(
                status=SpotifyDeviceStatus.NO_DEVICE,
                detail="No Spotify playback device is currently available.",
            )
        )
        executor = SpotifyPlaybackExecutor(
            SpotifyPlaybackCommand.PAUSE,
            client,  # type: ignore[arg-type]
            coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                self._validated(executor.action_id),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(client.calls, [])

    def test_provider_errors_are_sanitized(self) -> None:
        client = _PlaybackClient(error=SpotifyAPIError("private", status_code=403))
        executor = SpotifyPlaybackExecutor(
            SpotifyPlaybackCommand.NEXT,
            client,  # type: ignore[arg-type]
            _Coordinator(_ready(self.device)),  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                self._validated(executor.action_id),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertNotIn("private", result.summary)

    def test_cancelled_request_never_checks_device_or_api(self) -> None:
        token = ActionCancellationToken()
        token.cancel()
        client = _PlaybackClient()
        coordinator = _Coordinator(_ready(self.device))
        executor = SpotifyPlaybackExecutor(
            SpotifyPlaybackCommand.PLAY,
            client,  # type: ignore[arg-type]
            coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                self._validated(executor.action_id),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(coordinator.allow_activation, [])
        self.assertEqual(client.calls, [])

    def _validated(self, action_id: str):
        return self.validator.validate(
            ActionRequest(
                correlation_id="spotify-control-1",
                action_id=action_id,
                source="chat",
                parameters={"service": "spotify"},
            )
        )


class SpotifyPlaybackActionIntegrationTest(unittest.TestCase):
    def test_playback_is_denied_then_audited_after_exact_grant(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            path_policy = ProtectedPathPolicy()
            client = _PlaybackClient()
            executor = SpotifyPlaybackExecutor(
                SpotifyPlaybackCommand.PAUSE,
                client,  # type: ignore[arg-type]
                _Coordinator(_ready(_desktop_device())),  # type: ignore[arg-type]
            )
            service = AssistantActionService(
                ActionRequestValidator(build_default_action_registry(), path_policy),
                ActionPermissionPolicy(path_policy),
                repository,
                repository,
                executors=(executor,),
            )
            permissions = AssistantPermissionService(repository, path_policy)
            request = ActionRequest(
                correlation_id="spotify-integration-1",
                action_id="spotify.pause",
                source="chat",
                parameters={"service": "spotify"},
            )

            denied = asyncio.run(service.evaluate_request(request))
            asyncio.run(permissions.grant_spotify_playback())
            allowed = asyncio.run(service.evaluate_request(request))
            audits = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(denied.status, ActionStatus.DENIED)
        self.assertEqual(allowed.status, ActionStatus.SUCCESS)
        self.assertEqual(client.calls, [("pause", "desktop-id")])
        self.assertEqual(len(audits), 2)
        self.assertTrue(all(audit.normalized_target == "spotify" for audit in audits))


class SpotifyShuffleExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_shuffle_sets_only_the_validated_boolean_state(self) -> None:
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                client = _PlaybackClient()
                coordinator = _Coordinator(_ready(_desktop_device()))
                executor = SpotifyShuffleExecutor(
                    client,  # type: ignore[arg-type]
                    coordinator,  # type: ignore[arg-type]
                )
                action = self.validator.validate(
                    ActionRequest(
                        correlation_id=f"spotify-shuffle-{enabled}",
                        action_id="spotify.shuffle",
                        source="chat",
                        parameters={"service": "spotify", "enabled": enabled},
                    )
                )

                result = asyncio.run(
                    executor.execute(
                        action,
                        cancellation_token=ActionCancellationToken(),
                    )
                )

                self.assertEqual(result.status, ActionStatus.SUCCESS)
                self.assertEqual(client.shuffle_calls, [("desktop-id", enabled)])
                self.assertEqual(coordinator.allow_activation, [False])

    def test_shuffle_requires_a_boolean_state(self) -> None:
        with self.assertRaises(ActionValidationError):
            self.validator.validate(
                ActionRequest(
                    correlation_id="spotify-shuffle-invalid",
                    action_id="spotify.shuffle",
                    source="chat",
                    parameters={"service": "spotify", "enabled": "yes"},
                )
            )

    def test_shuffle_uses_existing_permission_and_is_audited(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            path_policy = ProtectedPathPolicy()
            client = _PlaybackClient()
            executor = SpotifyShuffleExecutor(
                client,  # type: ignore[arg-type]
                _Coordinator(_ready(_desktop_device())),  # type: ignore[arg-type]
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
                correlation_id="spotify-shuffle-audit",
                action_id="spotify.shuffle",
                source="voice",
                parameters={"service": "spotify", "enabled": True},
            )

            result = asyncio.run(service.evaluate_request(request))
            audits = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(client.shuffle_calls, [("desktop-id", True)])
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action_id, "spotify.shuffle")
        self.assertEqual(audits[0].normalized_target, "spotify")


class SpotifyRepeatExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_repeat_sets_only_allowlisted_modes(self) -> None:
        expected_summaries = {
            "track": "Spotify will repeat the current track.",
            "context": "Spotify will repeat the current album or playlist.",
            "off": "Spotify repeat was disabled.",
        }
        for mode in ("track", "context", "off"):
            with self.subTest(mode=mode):
                client = _PlaybackClient()
                coordinator = _Coordinator(_ready(_desktop_device()))
                executor = SpotifyRepeatExecutor(
                    client,  # type: ignore[arg-type]
                    coordinator,  # type: ignore[arg-type]
                )
                action = self.validator.validate(
                    ActionRequest(
                        correlation_id=f"spotify-repeat-{mode}",
                        action_id="spotify.repeat",
                        source="voice",
                        parameters={"service": "spotify", "mode": mode},
                    )
                )

                result = asyncio.run(
                    executor.execute(
                        action,
                        cancellation_token=ActionCancellationToken(),
                    )
                )

                self.assertEqual(result.status, ActionStatus.SUCCESS)
                self.assertEqual(result.summary, expected_summaries[mode])
                self.assertEqual(client.repeat_calls, [("desktop-id", mode)])
                self.assertEqual(coordinator.allow_activation, [False])

    def test_repeat_rejects_unallowlisted_mode_at_validation(self) -> None:
        with self.assertRaises(ActionValidationError):
            self.validator.validate(
                ActionRequest(
                    correlation_id="spotify-repeat-invalid",
                    action_id="spotify.repeat",
                    source="chat",
                    parameters={"service": "spotify", "mode": "all"},
                )
            )

    def test_repeat_uses_existing_permission_and_is_audited(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteActionRepository(Path(directory) / "akiha.sqlite3")
            path_policy = ProtectedPathPolicy()
            client = _PlaybackClient()
            executor = SpotifyRepeatExecutor(
                client,  # type: ignore[arg-type]
                _Coordinator(_ready(_desktop_device())),  # type: ignore[arg-type]
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
                correlation_id="spotify-repeat-audit",
                action_id="spotify.repeat",
                source="voice",
                parameters={"service": "spotify", "mode": "track"},
            )

            result = asyncio.run(service.evaluate_request(request))
            audits = asyncio.run(repository.get_recent_action_audits(limit=10))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(client.repeat_calls, [("desktop-id", "track")])
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0].action_id, "spotify.repeat")
        self.assertEqual(audits[0].normalized_target, "spotify")


class SpotifyVolumeExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_volume_uses_only_supported_device_and_bounded_percentage(self) -> None:
        client = _PlaybackClient()
        coordinator = _Coordinator(
            _ready(_desktop_device(supports_volume=True, volume_percent=35))
        )
        executor = SpotifyVolumeExecutor(
            client,  # type: ignore[arg-type]
            coordinator,  # type: ignore[arg-type]
        )
        action = self.validator.validate(
            ActionRequest(
                correlation_id="spotify-volume-65",
                action_id="spotify.volume",
                source="voice",
                parameters={"service": "spotify", "volume_percent": 65},
            )
        )

        result = asyncio.run(
            executor.execute(
                action,
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.summary, "Spotify volume was set to 65%.")
        self.assertEqual(client.volume_calls, [("desktop-id", 65)])
        self.assertEqual(coordinator.allow_activation, [False])

    def test_unsupported_device_fails_without_volume_request(self) -> None:
        client = _PlaybackClient()
        executor = SpotifyVolumeExecutor(
            client,  # type: ignore[arg-type]
            _Coordinator(_ready(_desktop_device())),  # type: ignore[arg-type]
        )
        action = self.validator.validate(
            ActionRequest(
                correlation_id="spotify-volume-unsupported",
                action_id="spotify.volume",
                source="chat",
                parameters={"service": "spotify", "volume_percent": 50},
            )
        )

        result = asyncio.run(
            executor.execute(
                action,
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertIn("does not support", result.summary)
        self.assertEqual(client.volume_calls, [])


class SpotifyArtistPlaybackExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )
        self.coordinator = _Coordinator(_ready(_desktop_device()))

    def test_exact_artist_match_starts_artist_context(self) -> None:
        client = _ArtistClient(
            (
                _artist("artist1", "Megurine Luka"),
                _artist("artist2", "Megurine Luka Tribute"),
            )
        )
        executor = SpotifyArtistPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                self._validated("Megurine Luka"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(client.searches, ["artist:Megurine Luka"])
        self.assertEqual(
            client.context_calls,
            [("desktop-id", "spotify:artist:artist1")],
        )
        self.assertIn("Megurine Luka", result.summary)

    def test_ambiguous_artist_returns_bounded_local_choices(self) -> None:
        candidates = (
            _artist("artist1", "Signal One"),
            _artist("artist2", "Signal Two"),
        )
        client = _ArtistClient(candidates)
        executor = SpotifyArtistPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                self._validated("Signal"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(result.metadata["artist_candidates"], candidates)
        self.assertEqual(client.context_calls, [])
        self.assertEqual(self.coordinator.allow_activation, [])

    def test_numbered_artist_follow_up_uses_selected_uri_without_search(self) -> None:
        artist = _artist("artist2", "Signal Two")
        store = SpotifyArtistSelectionStore()
        store.replace((_artist("artist1", "Signal One"), artist))
        request = store.parse_follow_up("Akiha, play artist result two.")
        self.assertIsNotNone(request)
        client = _ArtistClient(())
        executor = SpotifyArtistPlaybackExecutor(
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
            client.context_calls,
            [("desktop-id", "spotify:artist:artist2")],
        )

    def _validated(self, artist_query: str):
        return self.validator.validate(
            ActionRequest(
                correlation_id="spotify-artist-1",
                action_id="spotify.play_artist",
                source="chat",
                parameters={
                    "service": "spotify",
                    "artist_query": artist_query,
                },
            )
        )


class SpotifyArtistSearchExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_search_returns_bounded_artists_without_starting_playback(self) -> None:
        artists = tuple(
            _artist(f"artist{index}", f"Synthetic Artist {index}")
            for index in range(1, 6)
        )
        client = _ArtistClient(artists)
        executor = SpotifyArtistSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                self._validated("Synthetic Artist"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["artist_candidates"], artists)
        self.assertEqual(client.searches, ["artist:Synthetic Artist"])
        self.assertEqual(client.context_calls, [])

    def test_empty_search_is_a_successful_zero_result(self) -> None:
        client = _ArtistClient(())
        executor = SpotifyArtistSearchExecutor(client)  # type: ignore[arg-type]

        result = asyncio.run(
            executor.execute(
                self._validated("Missing Artist"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["artist_candidates"], ())
        self.assertIn("could not find", result.summary)

    def _validated(self, artist_query: str):
        return self.validator.validate(
            ActionRequest(
                correlation_id="spotify-artist-search-1",
                action_id="spotify.search_artists",
                source="chat",
                parameters={
                    "service": "spotify",
                    "artist_query": artist_query,
                },
            )
        )


class SpotifyArtistOpenExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_exact_artist_opens_page_without_playback_or_device_selection(self) -> None:
        client = _ArtistClient((_artist("ado123", "ADO"),))
        opened_ids: list[str] = []
        executor = SpotifyArtistOpenExecutor(
            client,  # type: ignore[arg-type]
            lambda artist_id: opened_ids.append(artist_id) is None,
        )

        result = asyncio.run(
            executor.execute(
                self._validated("ADO"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(opened_ids, ["ado123"])
        self.assertEqual(client.context_calls, [])

    def test_ambiguous_open_returns_choices_without_opening(self) -> None:
        candidates = (
            _artist("ado123", "ADO Tribute"),
            _artist("ado456", "ADO Covers"),
        )
        client = _ArtistClient(candidates)
        opened_ids: list[str] = []
        executor = SpotifyArtistOpenExecutor(
            client,  # type: ignore[arg-type]
            lambda artist_id: opened_ids.append(artist_id) is None,
        )

        result = asyncio.run(
            executor.execute(
                self._validated("ADO"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(result.metadata["artist_candidates"], candidates)
        self.assertEqual(opened_ids, [])

    def test_selection_store_preserves_open_only_intent(self) -> None:
        store = SpotifyArtistSelectionStore()
        store.replace(
            (_artist("ado123", "ADO"),),
            allowed_action_ids=("spotify.open_artist",),
        )

        open_request = store.parse_follow_up("Open artist result 1")
        play_request = store.parse_follow_up("Play artist result 1")

        self.assertIsNotNone(open_request)
        self.assertEqual(open_request.action_id, "spotify.open_artist")
        self.assertIsNone(play_request)

    def test_selection_store_reports_stale_and_out_of_range_results(self) -> None:
        store = SpotifyArtistSelectionStore()
        self.assertIn("no active", store.follow_up_error("Play artist result 11"))

        store.replace((_artist("ado123", "ADO"),))

        self.assertEqual(
            store.follow_up_error("Play artist result 11"),
            "Choose an artist result from 1 to 1.",
        )

    def test_default_opener_prefers_fixed_spotify_desktop_uri(self) -> None:
        with (
            patch("project_akiha.services.spotify_playback.os.startfile") as startfile,
            patch(
                "project_akiha.services.spotify_playback.webbrowser.open"
            ) as open_url,
        ):
            opened = _open_spotify_artist_page("Artist123")

        self.assertTrue(opened)
        startfile.assert_called_once_with("spotify:artist:Artist123")
        open_url.assert_not_called()

    def test_default_opener_falls_back_to_fixed_official_web_url(self) -> None:
        with (
            patch(
                "project_akiha.services.spotify_playback.os.startfile",
                side_effect=OSError("protocol unavailable"),
            ) as startfile,
            patch(
                "project_akiha.services.spotify_playback.webbrowser.open",
                return_value=True,
            ) as open_url,
        ):
            opened = _open_spotify_artist_page("Artist123")

        self.assertTrue(opened)
        startfile.assert_called_once_with("spotify:artist:Artist123")
        open_url.assert_called_once_with(
            "https://open.spotify.com/artist/Artist123",
            new=2,
            autoraise=True,
        )

    def test_default_opener_rejects_untrusted_artist_id(self) -> None:
        with self.assertRaises(ValueError):
            _open_spotify_artist_page("../attacker")

    def _validated(self, artist_query: str):
        return self.validator.validate(
            ActionRequest(
                correlation_id="spotify-artist-open-1",
                action_id="spotify.open_artist",
                source="chat",
                parameters={
                    "service": "spotify",
                    "artist_query": artist_query,
                },
            )
        )


class _PlaybackClient:
    def __init__(self, error: SpotifyAPIError | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.shuffle_calls: list[tuple[str, bool]] = []
        self.repeat_calls: list[tuple[str, str]] = []
        self.volume_calls: list[tuple[str, int]] = []
        self.error = error

    def _record(self, command: str, device_id: str) -> None:
        if self.error is not None:
            raise self.error
        self.calls.append((command, device_id))

    def start_or_resume_playback(self, device_id: str) -> None:
        self._record("play", device_id)

    def pause_playback(self, device_id: str) -> None:
        self._record("pause", device_id)

    def skip_to_next(self, device_id: str) -> None:
        self._record("next", device_id)

    def skip_to_previous(self, device_id: str) -> None:
        self._record("previous", device_id)

    def set_shuffle(self, device_id: str, enabled: bool) -> None:
        if self.error is not None:
            raise self.error
        self.shuffle_calls.append((device_id, enabled))

    def set_repeat(self, device_id: str, mode: str) -> None:
        if self.error is not None:
            raise self.error
        self.repeat_calls.append((device_id, mode))

    def set_volume(self, device_id: str, volume_percent: int) -> None:
        if self.error is not None:
            raise self.error
        self.volume_calls.append((device_id, volume_percent))


class _ArtistClient:
    def __init__(self, artists: tuple[SpotifyCatalogItem, ...]) -> None:
        self.artists = artists
        self.searches: list[str] = []
        self.context_calls: list[tuple[str, str]] = []

    def search(
        self,
        query: str,
        *,
        kinds: tuple[SpotifyItemKind, ...],
        limit_per_kind: int,
    ) -> SpotifySearchResult:
        self.searches.append(query)
        if kinds != (SpotifyItemKind.ARTIST,) or limit_per_kind != 5:
            raise AssertionError("Artist search was not bounded correctly.")
        return SpotifySearchResult(query=query, items=self.artists)

    def start_context_playback(self, device_id: str, context_uri: str) -> None:
        self.context_calls.append((device_id, context_uri))


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


def _ready(device: SpotifyDevice) -> SpotifyDeviceResolution:
    return SpotifyDeviceResolution(
        status=SpotifyDeviceStatus.READY,
        selected_device=device,
        candidate_count=1,
    )


def _desktop_device(
    *,
    supports_volume: bool = False,
    volume_percent: int | None = None,
) -> SpotifyDevice:
    return SpotifyDevice(
        device_id="desktop-id",
        name="Windows PC",
        device_type="computer",
        is_active=True,
        is_restricted=False,
        volume_percent=volume_percent,
        supports_volume=supports_volume,
    )


def _artist(spotify_id: str, name: str) -> SpotifyCatalogItem:
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.ARTIST,
        spotify_id=spotify_id,
        uri=f"spotify:artist:{spotify_id}",
        name=name,
    )


if __name__ == "__main__":
    unittest.main()
