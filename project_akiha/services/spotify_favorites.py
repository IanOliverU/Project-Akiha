"""Permission-gated Spotify Liked Songs and local favorites playback."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from project_akiha.core.actions import (
    SPOTIFY_PLAY_FAVORITES_ACTION,
    ActionCancellationToken,
    ActionExecutionResult,
    ActionFailureCategory,
    ActionStatus,
    ValidatedAction,
)
from project_akiha.services.spotify_auth import SpotifyOAuthError
from project_akiha.services.spotify_client import SpotifyAPIError, SpotifyClient
from project_akiha.services.spotify_devices import (
    SpotifyDeviceCoordinator,
    SpotifyDeviceResolution,
    SpotifyDeviceStatus,
)
from project_akiha.services.spotify_preferences import SpotifyPreferenceRanker


class SpotifyFavoritesPlaybackExecutor:
    """Play a bounded queue selected only from local account-derived metadata."""

    action_id = SPOTIFY_PLAY_FAVORITES_ACTION
    executor_id = "spotify_play_favorites"

    def __init__(
        self,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
        preference_ranker: SpotifyPreferenceRanker,
        *,
        retry_delay_seconds: float = 0.4,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not 0 <= retry_delay_seconds <= 5:
            raise ValueError("Spotify retry delay must be between 0 and 5 seconds.")
        self._client = client
        self._device_coordinator = device_coordinator
        self._preference_ranker = preference_ranker
        self._retry_delay_seconds = retry_delay_seconds
        self._sleeper = sleeper

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify favorites executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        mode = str(action.parameters["favorite_mode"])
        try:
            tracks = await self._preference_ranker.favorite_tracks(mode)
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before playing favorite music."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if not tracks:
            if mode == "liked":
                return _unavailable("Your Spotify Liked Songs queue is empty.")
            return _unavailable(
                "Spotify did not return enough listening activity for a favorites mix."
            )
        if cancellation_token.is_cancelled:
            return _cancelled()

        resolution = await self._device_coordinator.resolve(
            action.request.correlation_id,
            cancellation_token=cancellation_token,
            allow_activation=True,
        )
        if resolution.status is not SpotifyDeviceStatus.READY:
            return _resolution_failure(resolution)
        device = resolution.selected_device
        if device is None:
            return _unavailable("Spotify did not provide a usable playback device.")

        uris = tuple(track.uri for track in tracks[:50])
        for attempt in range(2):
            if cancellation_token.is_cancelled:
                return _cancelled()
            try:
                await asyncio.to_thread(
                    self._client.start_tracks_playback,
                    device.device_id,
                    uris,
                )
                break
            except SpotifyOAuthError:
                return _unavailable(
                    "Connect Spotify from Settings before using playback."
                )
            except SpotifyAPIError as error:
                if error.status_code != 404 or attempt > 0:
                    return _api_failure(error)
                await self._sleeper(self._retry_delay_seconds)
                refreshed = await self._device_coordinator.resolve(
                    action.request.correlation_id,
                    cancellation_token=cancellation_token,
                    allow_activation=False,
                )
                if refreshed.status is not SpotifyDeviceStatus.READY:
                    return _resolution_failure(refreshed)
                device = refreshed.selected_device
                if device is None:
                    return _unavailable(
                        "Spotify did not provide a usable playback device."
                    )

        label = "Liked Songs" if mode == "liked" else "local favorites mix"
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Playing {label} on Spotify ({len(uris)} tracks).",
            metadata={"favorite_mode": mode, "favorite_track_count": len(uris)},
        )


def build_spotify_favorites_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
    preference_ranker: SpotifyPreferenceRanker,
) -> tuple[SpotifyFavoritesPlaybackExecutor, ...]:
    return (
        SpotifyFavoritesPlaybackExecutor(
            client,
            device_coordinator,
            preference_ranker,
        ),
    )


def _resolution_failure(
    resolution: SpotifyDeviceResolution,
) -> ActionExecutionResult:
    if resolution.status is SpotifyDeviceStatus.CANCELLED:
        return _cancelled()
    if resolution.status is SpotifyDeviceStatus.APP_PERMISSION_REQUIRED:
        return ActionExecutionResult(
            status=ActionStatus.FAILED,
            summary=resolution.detail,
            failure_category=ActionFailureCategory.PERMISSION_REQUIRED,
        )
    return _unavailable(resolution.detail or "Spotify playback is unavailable.")


def _api_failure(error: SpotifyAPIError) -> ActionExecutionResult:
    if error.status_code == 403:
        summary = "Spotify denied favorites playback. Check account permissions."
    elif error.status_code == 404:
        summary = (
            "Spotify could not start the favorites queue. "
            "Make Spotify active and try again."
        )
    elif error.status_code == 429:
        summary = "Spotify temporarily rate-limited preference requests."
    else:
        summary = "Spotify favorite music could not be loaded."
    return _unavailable(summary)


def _unavailable(summary: str) -> ActionExecutionResult:
    return ActionExecutionResult(
        status=ActionStatus.FAILED,
        summary=summary,
        failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
    )


def _cancelled() -> ActionExecutionResult:
    return ActionExecutionResult(
        status=ActionStatus.CANCELLED,
        summary="Spotify favorites request was cancelled.",
    )
