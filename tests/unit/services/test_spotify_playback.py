"""Tests for typed Spotify playback action executors."""

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
    SpotifyArtistPlaybackExecutor,
    SpotifyArtistSelectionStore,
    SpotifyPlaybackCommand,
    SpotifyPlaybackExecutor,
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


class _PlaybackClient:
    def __init__(self, error: SpotifyAPIError | None = None) -> None:
        self.calls: list[tuple[str, str]] = []
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


def _desktop_device() -> SpotifyDevice:
    return SpotifyDevice(
        device_id="desktop-id",
        name="Windows PC",
        device_type="computer",
        is_active=True,
        is_restricted=False,
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
