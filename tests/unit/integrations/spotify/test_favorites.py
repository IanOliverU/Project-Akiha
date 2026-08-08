"""Tests for permission-gated Spotify favorites playback."""

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
from project_akiha.integrations.spotify.client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyDevice,
    SpotifyItemKind,
)
from project_akiha.integrations.spotify.devices import (
    SpotifyDeviceResolution,
    SpotifyDeviceStatus,
)
from project_akiha.integrations.spotify.favorites import (
    SpotifyFavoritesPlaybackExecutor,
)


class SpotifyFavoritesPlaybackExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )
        self.coordinator = _Coordinator()

    def test_liked_songs_start_only_the_validated_local_queue(self) -> None:
        tracks = (_track("one"), _track("two"))
        client = _FavoritesClient()
        executor = SpotifyFavoritesPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
            _Ranker({"liked": tracks}),  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "liked"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(
            client.queues,
            [("desktop-id", ("spotify:track:one", "spotify:track:two"))],
        )
        self.assertEqual(result.metadata["favorite_track_count"], 2)

    def test_empty_liked_songs_fail_without_resolving_a_device(self) -> None:
        executor = SpotifyFavoritesPlaybackExecutor(
            _FavoritesClient(),  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
            _Ranker({"liked": ()}),  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "liked"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertIn("Liked Songs", result.summary)
        self.assertEqual(self.coordinator.calls, [])

    def test_transient_404_refreshes_the_device_and_retries_once(self) -> None:
        client = _FavoritesClient(errors=[SpotifyAPIError("missing", status_code=404)])
        executor = SpotifyFavoritesPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
            _Ranker({"mix": (_track("favorite"),)}),  # type: ignore[arg-type]
            retry_delay_seconds=0,
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "mix"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(len(client.queues), 2)
        self.assertEqual(self.coordinator.calls, [True, False])

    def test_cancellation_never_loads_preferences_or_starts_playback(self) -> None:
        token = ActionCancellationToken()
        token.cancel()
        ranker = _Ranker({"mix": (_track("favorite"),)})
        client = _FavoritesClient()
        executor = SpotifyFavoritesPlaybackExecutor(
            client,  # type: ignore[arg-type]
            self.coordinator,  # type: ignore[arg-type]
            ranker,  # type: ignore[arg-type]
        )

        result = asyncio.run(
            executor.execute(
                _validated(self.validator, "mix"),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(ranker.calls, [])
        self.assertEqual(client.queues, [])


class _Ranker:
    def __init__(self, queues: dict[str, tuple[SpotifyCatalogItem, ...]]) -> None:
        self.queues = queues
        self.calls: list[str] = []

    async def favorite_tracks(self, mode: str) -> tuple[SpotifyCatalogItem, ...]:
        self.calls.append(mode)
        return self.queues.get(mode, ())


class _FavoritesClient:
    def __init__(self, *, errors: list[SpotifyAPIError] | None = None) -> None:
        self.errors = list(errors or [])
        self.queues: list[tuple[str, tuple[str, ...]]] = []

    def start_tracks_playback(
        self,
        device_id: str,
        track_uris: tuple[str, ...],
    ) -> None:
        self.queues.append((device_id, tuple(track_uris)))
        if self.errors:
            raise self.errors.pop(0)


class _Coordinator:
    def __init__(self) -> None:
        self.calls: list[bool] = []

    async def resolve(
        self,
        _correlation_id: str,
        *,
        cancellation_token: ActionCancellationToken,
        allow_activation: bool,
    ) -> SpotifyDeviceResolution:
        self.calls.append(allow_activation)
        if cancellation_token.is_cancelled:
            return SpotifyDeviceResolution(
                status=SpotifyDeviceStatus.CANCELLED,
                detail="cancelled",
            )
        return SpotifyDeviceResolution(
            status=SpotifyDeviceStatus.READY,
            detail="ready",
            selected_device=SpotifyDevice(
                device_id="desktop-id",
                name="Desktop",
                device_type="computer",
                is_active=True,
                is_restricted=False,
            ),
        )


def _validated(
    validator: ActionRequestValidator,
    mode: str,
):
    return validator.validate(
        ActionRequest(
            correlation_id=f"favorites-{mode}",
            action_id="spotify.play_favorites",
            source="chat",
            parameters={"service": "spotify", "favorite_mode": mode},
        )
    )


def _track(spotify_id: str) -> SpotifyCatalogItem:
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.TRACK,
        spotify_id=spotify_id,
        uri=f"spotify:track:{spotify_id}",
        name=f"Track {spotify_id}",
        artist_names=("Synthetic Artist",),
    )


if __name__ == "__main__":
    unittest.main()
