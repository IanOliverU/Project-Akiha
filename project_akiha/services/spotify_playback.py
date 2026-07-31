"""Typed Spotify playback executors behind Akiha's action boundary."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from difflib import SequenceMatcher
from enum import StrEnum
from uuid import uuid4

from project_akiha.core.actions import (
    SPOTIFY_NEXT_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_PLAY_ACTION,
    SPOTIFY_PLAY_ARTIST_ACTION,
    SPOTIFY_PREVIOUS_ACTION,
    SPOTIFY_RESUME_ACTION,
    SPOTIFY_SEARCH_ARTISTS_ACTION,
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
    r"^(?:(?:please|akiha[,.]?)\s+)*play\s+(?:spotify\s+)?artist\s+result\s+"
    r"(?P<index>\d+|one|two|three|four|five)[.!?]?$",
    re.IGNORECASE,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
_ARTIST_URI_PATTERN = re.compile(r"spotify:artist:[A-Za-z0-9]{1,64}\Z")


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
                search_result = await asyncio.to_thread(
                    self._client.search,
                    f"artist:{query}",
                    kinds=(SpotifyItemKind.ARTIST,),
                    limit_per_kind=5,
                )
            except SpotifyOAuthError:
                return _unavailable(
                    "Connect Spotify from Settings before searching for artists."
                )
            except SpotifyAPIError as error:
                return _api_failure(error)
            candidates = tuple(
                item for item in search_result.items if _is_valid_artist(item)
            )
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
            search_result = await asyncio.to_thread(
                self._client.search,
                f"artist:{query}",
                kinds=(SpotifyItemKind.ARTIST,),
                limit_per_kind=5,
            )
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for artists."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()

        candidates = tuple(
            item for item in search_result.items if _is_valid_artist(item)
        )[:5]
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

    @property
    def candidates(self) -> tuple[SpotifyCatalogItem, ...]:
        return self._candidates

    def replace(self, candidates: tuple[SpotifyCatalogItem, ...]) -> None:
        if len(candidates) > 5 or any(
            not _is_valid_artist(item) for item in candidates
        ):
            raise ValueError("artist selections require at most five artist items.")
        self._candidates = tuple(candidates)

    def clear(self) -> None:
        self._candidates = ()

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        match = _ARTIST_RESULT_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        raw_index = match.group("index").casefold()
        index = int(raw_index) if raw_index.isdigit() else _NUMBER_WORDS[raw_index]
        if index <= 0 or index > len(self._candidates):
            return None
        artist = self._candidates[index - 1]
        return ActionRequest(
            correlation_id=f"spotify-artist-result-{uuid4().hex}",
            action_id=SPOTIFY_PLAY_ARTIST_ACTION,
            source="spotify_followup",
            parameters={
                "service": "spotify",
                "artist_query": artist.name,
                "artist_name": artist.name,
                "artist_uri": artist.uri,
            },
        )


def build_spotify_playback_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
) -> tuple[
    SpotifyPlaybackExecutor
    | SpotifyArtistPlaybackExecutor
    | SpotifyArtistSearchExecutor,
    ...,
]:
    """Build one executor per registered Spotify action."""
    return (
        *(
            SpotifyPlaybackExecutor(command, client, device_coordinator)
            for command in SpotifyPlaybackCommand
        ),
        SpotifyArtistSearchExecutor(client),
        SpotifyArtistPlaybackExecutor(client, device_coordinator),
    )


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
