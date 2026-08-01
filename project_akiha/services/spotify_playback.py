"""Typed Spotify playback executors behind Akiha's action boundary."""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
import webbrowser
from collections.abc import Callable
from difflib import SequenceMatcher
from enum import StrEnum
from uuid import uuid4

from project_akiha.core.actions import (
    SPOTIFY_NEXT_ACTION,
    SPOTIFY_OPEN_ARTIST_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PLAY_ARTIST_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_REPEAT_ACTION,
    SPOTIFY_RESUME_ACTION,
    SPOTIFY_SEARCH_ARTISTS_ACTION,
    SPOTIFY_SHUFFLE_ACTION,
    SPOTIFY_VOLUME_ACTION,
    ActionCancellationToken,
    ActionExecutionResult,
    ActionFailureCategory,
    ActionRequest,
    ActionStatus,
    ValidatedAction,
)
from project_akiha.services.spotify_auth import SpotifyOAuthError
from project_akiha.services.spotify_client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyClient,
    SpotifyItemKind,
)
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

_ARTIST_RESULT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*(?P<verb>play|open)\s+"
    r"(?:spotify\s+)?artist\s+result\s+"
    r"(?P<index>\d+|one|two|three|four|five)[.!?]?$",
    re.IGNORECASE,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_ARTIST_URI_PATTERN = re.compile(r"spotify:artist:[A-Za-z0-9]{1,64}\Z")
_ARTIST_PAGE_URL_PREFIX = "https://open.spotify.com/artist/"
SpotifyArtistPageOpener = Callable[[str], bool]


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


class SpotifyShuffleExecutor:
    """Set an explicit shuffle state after validation and permission."""

    action_id = SPOTIFY_SHUFFLE_ACTION
    executor_id = "spotify_shuffle"

    def __init__(
        self,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
    ) -> None:
        self._client = client
        self._device_coordinator = device_coordinator

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify shuffle executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        enabled = action.parameters["enabled"]
        if not isinstance(enabled, bool):
            raise ValueError("Spotify shuffle state was not validated.")
        resolution = await self._device_coordinator.resolve(
            action.request.correlation_id,
            cancellation_token=cancellation_token,
            allow_activation=False,
        )
        if resolution.status is not SpotifyDeviceStatus.READY:
            return _resolution_failure(resolution)
        device = resolution.selected_device
        if device is None:
            return _unavailable("Spotify did not provide a usable playback device.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            await asyncio.to_thread(
                self._client.set_shuffle,
                device.device_id,
                enabled,
            )
        except SpotifyOAuthError:
            return _unavailable("Connect Spotify from Settings before using playback.")
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()
        state = "enabled" if enabled else "disabled"
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Spotify shuffle was {state}.",
        )


class SpotifyRepeatExecutor:
    """Set one validated Spotify repeat mode."""

    action_id = SPOTIFY_REPEAT_ACTION
    executor_id = "spotify_repeat"

    def __init__(
        self,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
    ) -> None:
        self._client = client
        self._device_coordinator = device_coordinator

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify repeat executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        mode = action.parameters["mode"]
        if not isinstance(mode, str) or mode not in {"track", "context", "off"}:
            raise ValueError("Spotify repeat mode was not validated.")
        resolution = await self._device_coordinator.resolve(
            action.request.correlation_id,
            cancellation_token=cancellation_token,
            allow_activation=False,
        )
        if resolution.status is not SpotifyDeviceStatus.READY:
            return _resolution_failure(resolution)
        device = resolution.selected_device
        if device is None:
            return _unavailable("Spotify did not provide a usable playback device.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            await asyncio.to_thread(
                self._client.set_repeat,
                device.device_id,
                mode,
            )
        except SpotifyOAuthError:
            return _unavailable("Connect Spotify from Settings before using playback.")
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()
        summaries = {
            "track": "Spotify will repeat the current track.",
            "context": "Spotify will repeat the current album or playlist.",
            "off": "Spotify repeat was disabled.",
        }
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=summaries[mode],
        )


class SpotifyVolumeExecutor:
    """Set bounded volume only when the selected device supports it."""

    action_id = SPOTIFY_VOLUME_ACTION
    executor_id = "spotify_volume"

    def __init__(
        self,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
    ) -> None:
        self._client = client
        self._device_coordinator = device_coordinator

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify volume executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        volume_percent = action.parameters["volume_percent"]
        if (
            not isinstance(volume_percent, int)
            or isinstance(volume_percent, bool)
            or not 0 <= volume_percent <= 100
        ):
            raise ValueError("Spotify volume was not validated.")
        resolution = await self._device_coordinator.resolve(
            action.request.correlation_id,
            cancellation_token=cancellation_token,
            allow_activation=False,
        )
        if resolution.status is not SpotifyDeviceStatus.READY:
            return _resolution_failure(resolution)
        device = resolution.selected_device
        if device is None:
            return _unavailable("Spotify did not provide a usable playback device.")
        if not device.supports_volume:
            return _unavailable(
                "The selected Spotify device does not support remote volume control."
            )
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            await asyncio.to_thread(
                self._client.set_volume,
                device.device_id,
                volume_percent,
            )
        except SpotifyOAuthError:
            return _unavailable("Connect Spotify from Settings before using playback.")
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Spotify volume was set to {volume_percent}%.",
        )


class SpotifyArtistPlaybackExecutor:
    """Resolve one artist locally, then start that Spotify artist context."""

    action_id = SPOTIFY_PLAY_ARTIST_ACTION
    executor_id = "spotify_play_artist"

    def __init__(
        self,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
    ) -> None:
        self._client = client
        self._device_coordinator = device_coordinator

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Search, resolve, and play without exposing catalog data to an AI."""
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify artist executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        selected = _selected_artist_from_action(action)
        if selected is None:
            query = str(action.parameters["artist_query"])
            try:
                candidates = await _search_artist_candidates(self._client, query)
            except SpotifyOAuthError:
                return _unavailable(
                    "Connect Spotify from Settings before searching for artists."
                )
            except SpotifyAPIError as error:
                return _api_failure(error)
            selected = _select_artist(query, candidates)
            if selected is None:
                if not candidates:
                    return _unavailable(
                        f'I could not find a Spotify artist matching "{query}".'
                    )
                return ActionExecutionResult(
                    status=ActionStatus.FAILED,
                    summary="I found several possible Spotify artists.",
                    failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                    metadata={"artist_candidates": candidates[:5]},
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
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            await asyncio.to_thread(
                self._client.start_context_playback,
                device.device_id,
                selected.uri,
            )
        except SpotifyOAuthError:
            return _unavailable("Connect Spotify from Settings before using playback.")
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Playing {selected.name}'s catalog on Spotify.",
            metadata={
                "artist_name": selected.name,
                "artist_uri": selected.uri,
            },
        )


class SpotifyArtistOpenExecutor:
    """Resolve one artist and open its fixed official Spotify page."""

    action_id = SPOTIFY_OPEN_ARTIST_ACTION
    executor_id = "spotify_open_artist"

    def __init__(
        self,
        client: SpotifyClient,
        opener: SpotifyArtistPageOpener | None = None,
    ) -> None:
        self._client = client
        self._opener = opener or _open_spotify_artist_page

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify artist-page executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        selected = _selected_artist_from_action(action)
        if selected is None:
            query = str(action.parameters["artist_query"])
            try:
                candidates = await _search_artist_candidates(self._client, query)
            except SpotifyOAuthError:
                return _unavailable(
                    "Connect Spotify from Settings before searching for artists."
                )
            except SpotifyAPIError as error:
                return _api_failure(error)
            selected = _select_artist(query, candidates)
            if selected is None:
                if not candidates:
                    return _unavailable(
                        f'I could not find a Spotify artist matching "{query}".'
                    )
                return ActionExecutionResult(
                    status=ActionStatus.FAILED,
                    summary="I found several possible Spotify artists.",
                    failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                    metadata={"artist_candidates": candidates[:5]},
                )

        if cancellation_token.is_cancelled:
            return _cancelled()
        try:
            opened = await asyncio.to_thread(self._opener, selected.spotify_id)
        except OSError:
            opened = False
        if not opened:
            return _unavailable("The Spotify artist page could not be opened.")
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Opened {selected.name}'s Spotify page.",
            metadata={
                "artist_name": selected.name,
                "artist_uri": selected.uri,
            },
        )


class SpotifyArtistSearchExecutor:
    """Return bounded local Spotify artist results without starting playback."""

    action_id = SPOTIFY_SEARCH_ARTISTS_ACTION
    executor_id = "spotify_search_artists"

    def __init__(self, client: SpotifyClient) -> None:
        self._client = client

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError(
                "Spotify artist-search executor received the wrong action."
            )
        if cancellation_token.is_cancelled:
            return _cancelled()

        query = str(action.parameters["artist_query"])
        try:
            candidates = await _search_artist_candidates(self._client, query)
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for artists."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()

        count = len(candidates)
        noun = "artist" if count == 1 else "artists"
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=(
                f"Found {count} Spotify {noun} matching {query}."
                if candidates
                else f'I could not find a Spotify artist matching "{query}".'
            ),
            metadata={"artist_candidates": candidates},
        )


class SpotifyArtistSelectionStore:
    """Retain bounded artist choices locally for an explicit numbered follow-up."""

    def __init__(self) -> None:
        self._candidates: tuple[SpotifyCatalogItem, ...] = ()
        self._allowed_action_ids = frozenset((SPOTIFY_PLAY_ARTIST_ACTION,))

    @property
    def candidates(self) -> tuple[SpotifyCatalogItem, ...]:
        return self._candidates

    def replace(
        self,
        candidates: tuple[SpotifyCatalogItem, ...],
        *,
        allowed_action_ids: tuple[str, ...] = (SPOTIFY_PLAY_ARTIST_ACTION,),
    ) -> None:
        if len(candidates) > 5 or any(
            not _is_valid_artist(item) for item in candidates
        ):
            raise ValueError("artist selections require at most five artist items.")
        allowed = frozenset(allowed_action_ids)
        if not allowed or not allowed.issubset(
            {SPOTIFY_PLAY_ARTIST_ACTION, SPOTIFY_OPEN_ARTIST_ACTION}
        ):
            raise ValueError("artist selections contain an unsupported follow-up.")
        self._candidates = tuple(candidates)
        self._allowed_action_ids = allowed

    def clear(self) -> None:
        self._candidates = ()
        self._allowed_action_ids = frozenset((SPOTIFY_PLAY_ARTIST_ACTION,))

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        match = _ARTIST_RESULT_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return None
        action_id = {
            "play": SPOTIFY_PLAY_ARTIST_ACTION,
            "open": SPOTIFY_OPEN_ARTIST_ACTION,
        }[match.group("verb").casefold()]
        if action_id not in self._allowed_action_ids:
            return None
        artist = self._candidates[index - 1]
        return ActionRequest(
            correlation_id=f"spotify-artist-result-{uuid4().hex}",
            action_id=action_id,
            source="spotify_followup",
            parameters={
                "service": "spotify",
                "artist_query": artist.name,
                "artist_name": artist.name,
                "artist_uri": artist.uri,
            },
        )

    def follow_up_error(self, text: str) -> str | None:
        """Explain a recognized artist result that cannot be fulfilled."""
        match = _ARTIST_RESULT_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        if not self._candidates:
            return (
                "There are no active Spotify artist results. "
                "Search for an artist first."
            )
        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return f"Choose an artist result from 1 to {len(self._candidates)}."
        action_id = {
            "play": SPOTIFY_PLAY_ARTIST_ACTION,
            "open": SPOTIFY_OPEN_ARTIST_ACTION,
        }[match.group("verb").casefold()]
        if action_id not in self._allowed_action_ids:
            allowed = (
                "opened"
                if SPOTIFY_OPEN_ARTIST_ACTION in self._allowed_action_ids
                else "played"
            )
            return f"Those artist results can only be {allowed}."
        return None


def build_spotify_playback_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
) -> tuple[
    SpotifyPlaybackExecutor
    | SpotifyShuffleExecutor
    | SpotifyRepeatExecutor
    | SpotifyVolumeExecutor
    | SpotifyArtistPlaybackExecutor
    | SpotifyArtistOpenExecutor
    | SpotifyArtistSearchExecutor,
    ...,
]:
    """Build one executor per registered Spotify action."""
    return (
        *(
            SpotifyPlaybackExecutor(command, client, device_coordinator)
            for command in SpotifyPlaybackCommand
        ),
        SpotifyShuffleExecutor(client, device_coordinator),
        SpotifyRepeatExecutor(client, device_coordinator),
        SpotifyVolumeExecutor(client, device_coordinator),
        SpotifyArtistSearchExecutor(client),
        SpotifyArtistOpenExecutor(client),
        SpotifyArtistPlaybackExecutor(client, device_coordinator),
    )


async def _search_artist_candidates(
    client: SpotifyClient,
    query: str,
) -> tuple[SpotifyCatalogItem, ...]:
    search_result = await asyncio.to_thread(
        client.search,
        f"artist:{query}",
        kinds=(SpotifyItemKind.ARTIST,),
        limit_per_kind=5,
    )
    return tuple(item for item in search_result.items if _is_valid_artist(item))[:5]


def _selected_artist_from_action(
    action: ValidatedAction,
) -> SpotifyCatalogItem | None:
    artist_name = action.parameters.get("artist_name")
    artist_uri = action.parameters.get("artist_uri")
    if artist_name is None and artist_uri is None:
        return None
    if not isinstance(artist_name, str) or not isinstance(artist_uri, str):
        return None
    if _ARTIST_URI_PATTERN.fullmatch(artist_uri) is None:
        return None
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.ARTIST,
        spotify_id=artist_uri.rsplit(":", 1)[-1],
        uri=artist_uri,
        name=artist_name,
    )


def _result_index(match: re.Match[str]) -> int:
    raw_index = match.group("index").casefold()
    return int(raw_index) if raw_index.isdigit() else _NUMBER_WORDS[raw_index]


def _select_artist(
    query: str,
    candidates: tuple[SpotifyCatalogItem, ...],
) -> SpotifyCatalogItem | None:
    query_key = _artist_key(query)
    exact = tuple(item for item in candidates if _artist_key(item.name) == query_key)
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None

    scored = sorted(
        (
            (SequenceMatcher(None, query_key, _artist_key(item.name)).ratio(), item)
            for item in candidates
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored:
        return None
    best_score, best_item = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score >= 0.82 and best_score - second_score >= 0.12:
        return best_item
    if len(scored) == 1 and best_score >= 0.75:
        return best_item
    return None


def _artist_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, re.UNICODE))


def _is_valid_artist(item: SpotifyCatalogItem) -> bool:
    return (
        item.kind is SpotifyItemKind.ARTIST
        and bool(item.name.strip())
        and _ARTIST_URI_PATTERN.fullmatch(item.uri) is not None
    )


def _open_spotify_artist_page(artist_id: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9]{1,64}", artist_id) is None:
        raise ValueError("Spotify artist ID is invalid.")
    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        try:
            startfile(f"spotify:artist:{artist_id}")
            return True
        except OSError:
            pass
    return webbrowser.open(
        f"{_ARTIST_PAGE_URL_PREFIX}{artist_id}",
        new=2,
        autoraise=True,
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
