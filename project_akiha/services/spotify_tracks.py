"""Bounded Spotify track search, selection, and playback actions."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Awaitable, Callable
from difflib import SequenceMatcher
from uuid import uuid4

from project_akiha.core.actions import (
    SPOTIFY_PLAY_TRACK_ACTION,
    SPOTIFY_SEARCH_TRACKS_ACTION,
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
from project_akiha.services.spotify_preferences import SpotifyPreferenceRanker

_TRACK_URI_PATTERN = re.compile(r"spotify:track:[A-Za-z0-9]{1,64}\Z")
_TRACK_RESULT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*play\s+(?:spotify\s+)?"
    r"(?:track|song)\s+result\s+"
    r"(?P<index>\d+|one|two|three|four|five)[.!?]?$",
    re.IGNORECASE,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


class SpotifyTrackSearchExecutor:
    """Return bounded local Spotify track results without starting playback."""

    action_id = SPOTIFY_SEARCH_TRACKS_ACTION
    executor_id = "spotify_search_tracks"

    def __init__(
        self,
        client: SpotifyClient,
        preference_ranker: SpotifyPreferenceRanker | None = None,
    ) -> None:
        self._client = client
        self._preference_ranker = preference_ranker

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify track-search executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        title = str(action.parameters["track_query"])
        artist = str(action.parameters.get("artist_query", ""))
        try:
            candidates = await _search_track_candidates(
                self._client,
                title,
                artist,
                self._preference_ranker,
            )
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for tracks."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()

        count = len(candidates)
        noun = "track" if count == 1 else "tracks"
        query_label = _query_label(title, artist)
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=(
                f"Found {count} Spotify {noun} matching {query_label}."
                if candidates
                else f'I could not find a Spotify track matching "{query_label}".'
            ),
            metadata={"track_candidates": candidates},
        )


class SpotifyTrackPlaybackExecutor:
    """Resolve one track locally, then play only its validated Spotify URI."""

    action_id = SPOTIFY_PLAY_TRACK_ACTION
    executor_id = "spotify_play_track"

    def __init__(
        self,
        client: SpotifyClient,
        device_coordinator: SpotifyDeviceCoordinator,
        preference_ranker: SpotifyPreferenceRanker | None = None,
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
            raise ValueError("Spotify track executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        selected = _selected_track_from_action(action)
        if selected is None:
            title = str(action.parameters["track_query"])
            artist = str(action.parameters.get("artist_query", ""))
            try:
                candidates = await _search_track_candidates(
                    self._client,
                    title,
                    artist,
                    self._preference_ranker,
                )
            except SpotifyOAuthError:
                return _unavailable(
                    "Connect Spotify from Settings before searching for tracks."
                )
            except SpotifyAPIError as error:
                return _api_failure(error)
            selected = _select_track(title, artist, candidates)
            if selected is None:
                if not candidates:
                    return _unavailable(
                        "I could not find a matching playable Spotify track."
                    )
                return ActionExecutionResult(
                    status=ActionStatus.FAILED,
                    summary="I found several possible Spotify tracks.",
                    failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                    metadata={"track_candidates": candidates},
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
        selected_device = resolution.selected_device
        if selected_device is None:
            return _unavailable("Spotify did not provide a usable playback device.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        for attempt in range(2):
            try:
                await asyncio.to_thread(
                    self._client.start_track_playback,
                    selected_device.device_id,
                    selected.uri,
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
                if cancellation_token.is_cancelled:
                    return _cancelled()
                refreshed = await self._device_coordinator.resolve(
                    action.request.correlation_id,
                    cancellation_token=cancellation_token,
                    allow_activation=False,
                )
                if refreshed.status is not SpotifyDeviceStatus.READY:
                    return _resolution_failure(refreshed)
                selected_device = refreshed.selected_device
                if selected_device is None:
                    return _unavailable(
                        "Spotify did not provide a usable playback device."
                    )
        if cancellation_token.is_cancelled:
            return _cancelled()
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Playing {selected.display_label} on Spotify.",
            metadata={
                "track_name": selected.name,
                "track_uri": selected.uri,
            },
        )


class SpotifyTrackSelectionStore:
    """Retain bounded track choices locally for explicit numbered playback."""

    def __init__(self) -> None:
        self._candidates: tuple[SpotifyCatalogItem, ...] = ()

    @property
    def candidates(self) -> tuple[SpotifyCatalogItem, ...]:
        return self._candidates

    def replace(self, candidates: tuple[SpotifyCatalogItem, ...]) -> None:
        if len(candidates) > 5 or any(not _is_valid_track(item) for item in candidates):
            raise ValueError("track selections require at most five playable tracks.")
        self._candidates = tuple(candidates)

    def clear(self) -> None:
        self._candidates = ()

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        match = _TRACK_RESULT_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return None
        track = self._candidates[index - 1]
        artist = track.artist_names[0] if track.artist_names else ""
        parameters = {
            "service": "spotify",
            "track_query": track.name,
            "track_name": track.name,
            "track_uri": track.uri,
        }
        if artist:
            parameters["artist_query"] = artist
            parameters["track_artist"] = artist
        return ActionRequest(
            correlation_id=f"spotify-track-result-{uuid4().hex}",
            action_id=SPOTIFY_PLAY_TRACK_ACTION,
            source="spotify_followup",
            parameters=parameters,
        )

    def follow_up_error(self, text: str) -> str | None:
        """Explain a recognized track result that is stale or out of range."""
        match = _TRACK_RESULT_PATTERN.fullmatch(text.strip())
        if match is None:
            return None
        if not self._candidates:
            return (
                "There are no active Spotify track results. Search for a track first."
            )
        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return f"Choose a track result from 1 to {len(self._candidates)}."
        return None


def build_spotify_track_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[SpotifyTrackSearchExecutor | SpotifyTrackPlaybackExecutor, ...]:
    return (
        SpotifyTrackSearchExecutor(client, preference_ranker),
        SpotifyTrackPlaybackExecutor(
            client,
            device_coordinator,
            preference_ranker,
        ),
    )


async def _search_track_candidates(
    client: SpotifyClient,
    title: str,
    artist: str,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[SpotifyCatalogItem, ...]:
    query = f"track:{title}"
    if artist:
        query = f"{query} artist:{artist}"
    search_result = await asyncio.to_thread(
        client.search,
        query,
        kinds=(SpotifyItemKind.TRACK,),
        limit_per_kind=5,
    )
    candidates = tuple(item for item in search_result.items if _is_valid_track(item))[
        :5
    ]
    if candidates:
        return await _rank_candidates(preference_ranker, candidates)

    relaxed_query = " ".join(part for part in (title, artist) if part).strip()
    if relaxed_query == query:
        return ()
    relaxed_result = await asyncio.to_thread(
        client.search,
        relaxed_query,
        kinds=(SpotifyItemKind.TRACK,),
        limit_per_kind=5,
    )
    candidates = tuple(item for item in relaxed_result.items if _is_valid_track(item))[
        :5
    ]
    return await _rank_candidates(preference_ranker, candidates)


async def _rank_candidates(
    preference_ranker: SpotifyPreferenceRanker | None,
    candidates: tuple[SpotifyCatalogItem, ...],
) -> tuple[SpotifyCatalogItem, ...]:
    if preference_ranker is None:
        return candidates
    return await preference_ranker.rank(candidates)


def _selected_track_from_action(action: ValidatedAction) -> SpotifyCatalogItem | None:
    track_name = action.parameters.get("track_name")
    track_uri = action.parameters.get("track_uri")
    track_artist = action.parameters.get("track_artist", "")
    if track_name is None and track_uri is None:
        return None
    if not isinstance(track_name, str) or not isinstance(track_uri, str):
        return None
    if not isinstance(track_artist, str):
        return None
    if _TRACK_URI_PATTERN.fullmatch(track_uri) is None:
        return None
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.TRACK,
        spotify_id=track_uri.rsplit(":", 1)[-1],
        uri=track_uri,
        name=track_name,
        artist_names=(track_artist,) if track_artist else (),
    )


def _result_index(match: re.Match[str]) -> int:
    raw_index = match.group("index").casefold()
    return int(raw_index) if raw_index.isdigit() else _NUMBER_WORDS[raw_index]


def _select_track(
    title: str,
    artist: str,
    candidates: tuple[SpotifyCatalogItem, ...],
) -> SpotifyCatalogItem | None:
    title_key = _text_key(title)
    artist_key = _text_key(artist)
    exact = tuple(
        item
        for item in candidates
        if _text_key(item.name) == title_key
        and (
            not artist_key
            or any(_text_key(name) == artist_key for name in item.artist_names)
        )
    )
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None

    scored: list[tuple[float, float, SpotifyCatalogItem]] = []
    for item in candidates:
        title_score = SequenceMatcher(None, title_key, _text_key(item.name)).ratio()
        artist_score = (
            max(
                (
                    SequenceMatcher(None, artist_key, _text_key(name)).ratio()
                    for name in item.artist_names
                ),
                default=0.0,
            )
            if artist_key
            else 1.0
        )
        combined = (
            title_score if not artist_key else 0.75 * title_score + 0.25 * artist_score
        )
        scored.append((combined, title_score, item))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    if not scored:
        return None
    best_score, best_title_score, best_item = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if (
        best_score >= 0.84
        and best_title_score >= 0.82
        and best_score - second_score >= 0.10
    ):
        return best_item
    if len(scored) == 1 and best_score >= 0.76 and best_title_score >= 0.78:
        return best_item
    return None


def _text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, re.UNICODE))


def _is_valid_track(item: SpotifyCatalogItem) -> bool:
    return (
        item.kind is SpotifyItemKind.TRACK
        and item.is_playable
        and bool(item.name.strip())
        and _TRACK_URI_PATTERN.fullmatch(item.uri) is not None
    )


def _query_label(title: str, artist: str) -> str:
    return f"{title} by {artist}" if artist else title


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
        summary = "Spotify denied the track request. Check account access."
    elif error.status_code == 404:
        summary = (
            "Spotify found the track, but the playback device could not start it. "
            "Make Spotify active and try again."
        )
    elif error.status_code == 429:
        summary = "Spotify temporarily rate-limited track requests."
    else:
        summary = "The Spotify track request could not be completed."
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
        summary="Spotify track request was cancelled.",
    )
