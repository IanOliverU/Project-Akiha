"""Bounded Spotify playlist discovery, selection, and playback."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Awaitable, Callable
from difflib import SequenceMatcher
from uuid import uuid4

from project_akiha.core.actions import (
    SPOTIFY_PLAY_PLAYLIST_ACTION,
    SPOTIFY_SEARCH_PLAYLISTS_ACTION,
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

_PLAYLIST_URI_PATTERN = re.compile(r"spotify:playlist:[A-Za-z0-9]{1,64}\Z")
_PLAYLIST_RESULT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*play\s+(?:spotify\s+)?"
    r"playlist\s+result\s+"
    r"(?P<index>\d+|one|two|three|four|five)[.!?]?$",
    re.IGNORECASE,
)
_PLAYLIST_CONTEXT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*play\s+"
    r"(?:that|this|the|same|the\s+same)\s+playlist"
    r"(?:\s+on\s+spotify)?[.!?]?$",
    re.IGNORECASE,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


class SpotifyPlaylistSearchExecutor:
    """Return bounded personal and catalog playlist metadata."""

    action_id = SPOTIFY_SEARCH_PLAYLISTS_ACTION
    executor_id = "spotify_search_playlists"

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
            raise ValueError(
                "Spotify playlist-search executor received the wrong action."
            )
        if cancellation_token.is_cancelled:
            return _cancelled()

        query = str(action.parameters["playlist_query"])
        try:
            candidates = await _search_playlist_candidates(
                self._client,
                query,
                self._preference_ranker,
            )
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for playlists."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()

        count = len(candidates)
        noun = "playlist" if count == 1 else "playlists"
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=(
                f'Found {count} Spotify {noun} matching "{query}".'
                if candidates
                else f'I could not find a Spotify playlist matching "{query}".'
            ),
            metadata={"playlist_candidates": candidates},
        )


class SpotifyPlaylistPlaybackExecutor:
    """Resolve one playlist locally and play its validated context URI."""

    action_id = SPOTIFY_PLAY_PLAYLIST_ACTION
    executor_id = "spotify_play_playlist"

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
            raise ValueError("Spotify playlist executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        selected = _selected_playlist_from_action(action)
        if selected is None:
            query = str(action.parameters["playlist_query"])
            try:
                candidates = await _search_playlist_candidates(
                    self._client,
                    query,
                    self._preference_ranker,
                )
            except SpotifyOAuthError:
                return _unavailable(
                    "Connect Spotify from Settings before searching for playlists."
                )
            except SpotifyAPIError as error:
                return _api_failure(error)
            selected = _select_playlist(query, candidates)
            if selected is None:
                if not candidates:
                    return _unavailable(
                        f'I could not find a Spotify playlist matching "{query}".'
                    )
                return ActionExecutionResult(
                    status=ActionStatus.FAILED,
                    summary="I found several possible Spotify playlists.",
                    failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
                    metadata={"playlist_candidates": candidates},
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

        for attempt in range(2):
            if cancellation_token.is_cancelled:
                return _cancelled()
            try:
                await asyncio.to_thread(
                    self._client.start_context_playback,
                    device.device_id,
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

        owner = f" - {selected.owner_name}" if selected.owner_name else ""
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Playing playlist {selected.name}{owner} on Spotify.",
            metadata={
                "playlist_name": selected.name,
                "playlist_uri": selected.uri,
                "playlist_owner": selected.owner_name,
            },
        )


class SpotifyPlaylistSelectionStore:
    """Retain bounded playlist choices and one short-lived selected playlist."""

    def __init__(self) -> None:
        self._candidates: tuple[SpotifyCatalogItem, ...] = ()
        self._last_selected: SpotifyCatalogItem | None = None

    @property
    def candidates(self) -> tuple[SpotifyCatalogItem, ...]:
        return self._candidates

    def replace(self, candidates: tuple[SpotifyCatalogItem, ...]) -> None:
        if len(candidates) > 5 or any(
            not _is_valid_playlist(item) for item in candidates
        ):
            raise ValueError("playlist selections require at most five playlists.")
        self._candidates = tuple(candidates)
        self._last_selected = None

    def remember_selected(
        self,
        playlist_name: str,
        playlist_uri: str,
        playlist_owner: str = "",
    ) -> None:
        playlist = SpotifyCatalogItem(
            kind=SpotifyItemKind.PLAYLIST,
            spotify_id=playlist_uri.rsplit(":", 1)[-1],
            uri=playlist_uri,
            name=playlist_name,
            owner_name=playlist_owner,
        )
        if not _is_valid_playlist(playlist):
            raise ValueError("the selected Spotify playlist is invalid.")
        self._last_selected = playlist

    def clear_candidates(self) -> None:
        self._candidates = ()

    def clear(self) -> None:
        self.clear_candidates()
        self._last_selected = None

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        normalized = text.strip()
        match = _PLAYLIST_RESULT_PATTERN.fullmatch(normalized)
        if match is not None:
            index = _result_index(match)
            if index <= 0 or index > len(self._candidates):
                return None
            return _playlist_action_request(
                self._candidates[index - 1],
                source="spotify_followup",
                correlation_prefix="spotify-playlist-result",
            )

        context_match = _PLAYLIST_CONTEXT_PATTERN.fullmatch(normalized)
        if context_match is None or self._last_selected is None:
            return None
        return _playlist_action_request(
            self._last_selected,
            source="spotify_context_followup",
            correlation_prefix="spotify-playlist-context",
        )

    def follow_up_error(self, text: str) -> str | None:
        normalized = text.strip()
        if (
            _PLAYLIST_CONTEXT_PATTERN.fullmatch(normalized) is not None
            and self._last_selected is None
        ):
            return (
                "There is no recent Spotify playlist to use. "
                "Search for or play a playlist first."
            )
        match = _PLAYLIST_RESULT_PATTERN.fullmatch(normalized)
        if match is None:
            return None
        if not self._candidates:
            return (
                "There are no active Spotify playlist results. "
                "Search for a playlist first."
            )
        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return f"Choose a playlist result from 1 to {len(self._candidates)}."
        return None


def build_spotify_playlist_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[SpotifyPlaylistSearchExecutor | SpotifyPlaylistPlaybackExecutor, ...]:
    return (
        SpotifyPlaylistSearchExecutor(client, preference_ranker),
        SpotifyPlaylistPlaybackExecutor(
            client,
            device_coordinator,
            preference_ranker,
        ),
    )


async def _search_playlist_candidates(
    client: SpotifyClient,
    query: str,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[SpotifyCatalogItem, ...]:
    library, catalog = await asyncio.gather(
        asyncio.to_thread(client.get_playlists, max_items=200),
        asyncio.to_thread(
            client.search,
            query,
            kinds=(SpotifyItemKind.PLAYLIST,),
            limit_per_kind=5,
        ),
    )
    query_key = _text_key(query)
    library_matches = sorted(
        (
            (_playlist_score(query_key, item), item)
            for item in library
            if _is_valid_playlist(item) and _playlist_score(query_key, item) >= 0.45
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    combined = [item for _score, item in library_matches]
    combined.extend(item for item in catalog.items if _is_valid_playlist(item))
    candidates = _deduplicate_playlists(combined)[:5]
    if preference_ranker is None:
        return candidates
    return await preference_ranker.rank(candidates)


def _selected_playlist_from_action(
    action: ValidatedAction,
) -> SpotifyCatalogItem | None:
    playlist_name = action.parameters.get("playlist_name")
    playlist_uri = action.parameters.get("playlist_uri")
    playlist_owner = action.parameters.get("playlist_owner", "")
    if playlist_name is None and playlist_uri is None:
        return None
    if not isinstance(playlist_name, str) or not isinstance(playlist_uri, str):
        return None
    if not isinstance(playlist_owner, str):
        return None
    playlist = SpotifyCatalogItem(
        kind=SpotifyItemKind.PLAYLIST,
        spotify_id=playlist_uri.rsplit(":", 1)[-1],
        uri=playlist_uri,
        name=playlist_name,
        owner_name=playlist_owner,
    )
    return playlist if _is_valid_playlist(playlist) else None


def _select_playlist(
    query: str,
    candidates: tuple[SpotifyCatalogItem, ...],
) -> SpotifyCatalogItem | None:
    query_key = _text_key(query)
    exact = tuple(item for item in candidates if _text_key(item.name) == query_key)
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None

    scored = sorted(
        ((_playlist_score(query_key, item), item) for item in candidates),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored:
        return None
    best_score, best_item = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score >= 0.86 and best_score - second_score >= 0.12:
        return best_item
    if len(scored) == 1 and best_score >= 0.78:
        return best_item
    return None


def _playlist_action_request(
    playlist: SpotifyCatalogItem,
    *,
    source: str,
    correlation_prefix: str,
) -> ActionRequest:
    return ActionRequest(
        correlation_id=f"{correlation_prefix}-{uuid4().hex}",
        action_id=SPOTIFY_PLAY_PLAYLIST_ACTION,
        source=source,
        parameters={
            "service": "spotify",
            "playlist_query": playlist.name,
            "playlist_name": playlist.name,
            "playlist_uri": playlist.uri,
            "playlist_owner": playlist.owner_name,
        },
    )


def _deduplicate_playlists(
    playlists: list[SpotifyCatalogItem],
) -> tuple[SpotifyCatalogItem, ...]:
    seen: set[str] = set()
    unique: list[SpotifyCatalogItem] = []
    for playlist in playlists:
        if playlist.uri in seen:
            continue
        seen.add(playlist.uri)
        unique.append(playlist)
    return tuple(unique)


def _playlist_score(query_key: str, playlist: SpotifyCatalogItem) -> float:
    return SequenceMatcher(None, query_key, _text_key(playlist.name)).ratio()


def _text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, re.UNICODE))


def _is_valid_playlist(item: SpotifyCatalogItem) -> bool:
    return (
        item.kind is SpotifyItemKind.PLAYLIST
        and bool(item.name.strip())
        and _PLAYLIST_URI_PATTERN.fullmatch(item.uri) is not None
    )


def _result_index(match: re.Match[str]) -> int:
    raw_index = match.group("index").casefold()
    return int(raw_index) if raw_index.isdigit() else _NUMBER_WORDS[raw_index]


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
        summary = "Spotify denied the playlist request. Check account access."
    elif error.status_code == 404:
        summary = (
            "Spotify found the playlist, but the playback device could not start it. "
            "Make Spotify active and try again."
        )
    elif error.status_code == 429:
        summary = "Spotify temporarily rate-limited playlist requests."
    else:
        summary = "The Spotify playlist request could not be completed."
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
        summary="Spotify playlist request was cancelled.",
    )
