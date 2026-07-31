"""Typed Spotify playback executors behind Akiha's action boundary."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from project_akiha.core.actions import (
    SPOTIFY_NEXT_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_RESUME_ACTION,
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


class SpotifyPlaybackCommand(StrEnum):
    """Playback controls supported by the first Spotify action slice."""

    PLAY = "play"
    PAUSE = "pause"
    RESUME = "resume"
    NEXT = "next"
    PREVIOUS = "previous"


_ACTION_IDS = {
    SpotifyPlaybackCommand.PLAY: SPOTIFY_PLAY_ACTION,
    SpotifyPlaybackCommand.PAUSE: SPOTIFY_PAUSE_ACTION,
    SpotifyPlaybackCommand.RESUME: SPOTIFY_RESUME_ACTION,
    SpotifyPlaybackCommand.NEXT: SPOTIFY_NEXT_ACTION,
    SpotifyPlaybackCommand.PREVIOUS: SPOTIFY_PREVIOUS_ACTION,
}

_SUCCESS_SUMMARIES = {
    SpotifyPlaybackCommand.PLAY: "Spotify playback was started.",
    SpotifyPlaybackCommand.PAUSE: "Spotify playback was paused.",
    SpotifyPlaybackCommand.RESUME: "Spotify playback was resumed.",
    SpotifyPlaybackCommand.NEXT: "Spotify skipped to the next track.",
    SpotifyPlaybackCommand.PREVIOUS: "Spotify returned to the previous track.",
}


class SpotifyPlaybackExecutor:
    """Execute one exact Spotify control after validation and permission."""

    def __init__(
        self,
        command: SpotifyPlaybackCommand,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
    ) -> None:
        self.command = SpotifyPlaybackCommand(command)
        self.action_id = _ACTION_IDS[self.command]
        self.executor_id = f"spotify_{self.command.value}"
        self._client = client
        self._device_coordinator = device_coordinator

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Resolve a fresh device and send one bounded Spotify API mutation."""
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        resolution = await self._device_coordinator.resolve(
            action.request.correlation_id,
            cancellation_token=cancellation_token,
            allow_activation=self.command
            in {SpotifyPlaybackCommand.PLAY, SpotifyPlaybackCommand.RESUME},
        )
        if resolution.status is not SpotifyDeviceStatus.READY:
            return _resolution_failure(resolution)
        device = resolution.selected_device
        if device is None:
            return _unavailable("Spotify did not provide a usable playback device.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            await asyncio.to_thread(self._execute_control, device.device_id)
        except SpotifyOAuthError:
            return _unavailable("Connect Spotify from Settings before using playback.")
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=_SUCCESS_SUMMARIES[self.command],
        )

    def _execute_control(self, device_id: str) -> None:
        if self.command in {
            SpotifyPlaybackCommand.PLAY,
            SpotifyPlaybackCommand.RESUME,
        }:
            self._client.start_or_resume_playback(device_id)
        elif self.command is SpotifyPlaybackCommand.PAUSE:
            self._client.pause_playback(device_id)
        elif self.command is SpotifyPlaybackCommand.NEXT:
            self._client.skip_to_next(device_id)
        else:
            self._client.skip_to_previous(device_id)


def build_spotify_playback_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
) -> tuple[SpotifyPlaybackExecutor, ...]:
    """Build one executor per registered Spotify action."""
    return tuple(
        SpotifyPlaybackExecutor(command, client, device_coordinator)
        for command in SpotifyPlaybackCommand
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
        summary = "Spotify denied playback. Check Premium access and permissions."
    elif error.status_code == 404:
        summary = "The selected Spotify device is no longer available."
    elif error.status_code == 429:
        summary = "Spotify temporarily rate-limited playback controls."
    else:
        summary = "Spotify playback could not be changed."
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
        summary="Spotify playback control was cancelled.",
    )
