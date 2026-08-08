"""Bounded Spotify album search, opening, selection, and playback."""

from __future__ import annotations

import asyncio
import os
import re
import unicodedata
import webbrowser
from collections.abc import Awaitable, Callable
from difflib import SequenceMatcher
from uuid import uuid4

from project_akiha.core.actions import (
    SPOTIFY_OPEN_ALBUM_ACTION,
    SPOTIFY_PLAY_ALBUM_ACTION,
    SPOTIFY_SEARCH_ALBUMS_ACTION,
    ActionCancellationToken,
    ActionExecutionResult,
    ActionFailureCategory,
    ActionRequest,
    ActionStatus,
    ValidatedAction,
)
from project_akiha.integrations.spotify.auth import SpotifyOAuthError
from project_akiha.integrations.spotify.client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyClient,
    SpotifyItemKind,
)
from project_akiha.integrations.spotify.devices import (
    SpotifyDeviceCoordinator,
    SpotifyDeviceResolution,
    SpotifyDeviceStatus,
)
from project_akiha.integrations.spotify.preferences import SpotifyPreferenceRanker

_ALBUM_URI_PATTERN = re.compile(r"spotify:album:[A-Za-z0-9]{1,64}\Z")
_ALBUM_RESULT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*(?P<verb>play|open)\s+"
    r"(?:spotify\s+)?album\s+result\s+"
    r"(?P<index>\d+|one|two|three|four|five)[.!?]?$",
    re.IGNORECASE,
)
_ALBUM_CONTEXT_PATTERN = re.compile(
    r"^(?:(?:please|akiha[,.]?)\s+)*(?P<verb>play|open)\s+"
    r"(?:that|this|the|same|the\s+same)\s+album"
    r"(?:\s+on\s+spotify)?[.!?]?$",
    re.IGNORECASE,
)
_ALBUM_PAGE_URL_PREFIX = "https://open.spotify.com/album/"
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
SpotifyAlbumPageOpener = Callable[[str], bool]


class SpotifyAlbumSearchExecutor:
    """Return bounded album metadata without opening or playing anything."""

    action_id = SPOTIFY_SEARCH_ALBUMS_ACTION
    executor_id = "spotify_search_albums"

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
            raise ValueError("Spotify album-search executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        title, artist = _album_query(action)
        try:
            candidates = await _search_album_candidates(
                self._client,
                title,
                artist,
                self._preference_ranker,
            )
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for albums."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if cancellation_token.is_cancelled:
            return _cancelled()

        count = len(candidates)
        noun = "album" if count == 1 else "albums"
        label = _query_label(title, artist)
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=(
                f"Found {count} Spotify {noun} matching {label}."
                if candidates
                else f'I could not find a Spotify album matching "{label}".'
            ),
            metadata={"album_candidates": candidates},
        )


class SpotifyAlbumOpenExecutor:
    """Resolve one album locally and open it in Spotify desktop first."""

    action_id = SPOTIFY_OPEN_ALBUM_ACTION
    executor_id = "spotify_open_album"

    def __init__(
        self,
        client: SpotifyClient,
        opener: SpotifyAlbumPageOpener | None = None,
        *,
        preference_ranker: SpotifyPreferenceRanker | None = None,
    ) -> None:
        self._client = client
        self._preference_ranker = preference_ranker
        self._opener = opener or _open_spotify_album_page

    async def execute(
        self,
        action: ValidatedAction,
        *,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        if action.definition.action_id != self.action_id:
            raise ValueError("Spotify album-page executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            selected, candidates = await _resolve_album(
                self._client,
                action,
                self._preference_ranker,
            )
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for albums."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if selected is None:
            return _unresolved_album(action, candidates)
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            opened = await asyncio.to_thread(self._opener, selected.spotify_id)
        except OSError:
            opened = False
        if not opened:
            return _unavailable("The Spotify album page could not be opened.")
        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Opened {selected.display_label} on Spotify.",
            metadata={
                "album_name": selected.name,
                "album_uri": selected.uri,
                "album_artist": (
                    selected.artist_names[0] if selected.artist_names else ""
                ),
            },
        )


class SpotifyAlbumPlaybackExecutor:
    """Resolve one album locally and play its validated Spotify context URI."""

    action_id = SPOTIFY_PLAY_ALBUM_ACTION
    executor_id = "spotify_play_album"

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
            raise ValueError("Spotify album executor received the wrong action.")
        if cancellation_token.is_cancelled:
            return _cancelled()

        try:
            selected, candidates = await _resolve_album(
                self._client,
                action,
                self._preference_ranker,
            )
        except SpotifyOAuthError:
            return _unavailable(
                "Connect Spotify from Settings before searching for albums."
            )
        except SpotifyAPIError as error:
            return _api_failure(error)
        if selected is None:
            return _unresolved_album(action, candidates)
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

        for attempt in range(2):
            if cancellation_token.is_cancelled:
                return _cancelled()
            try:
                await asyncio.to_thread(
                    self._client.start_context_playback,
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

        return ActionExecutionResult(
            status=ActionStatus.SUCCESS,
            summary=f"Playing album {selected.display_label} on Spotify.",
            metadata={
                "album_name": selected.name,
                "album_uri": selected.uri,
                "album_artist": (
                    selected.artist_names[0] if selected.artist_names else ""
                ),
            },
        )


class SpotifyAlbumSelectionStore:
    """Retain at most five albums for explicit play or open follow-ups."""

    def __init__(self) -> None:
        self._candidates: tuple[SpotifyCatalogItem, ...] = ()
        self._allowed_action_ids = frozenset((SPOTIFY_PLAY_ALBUM_ACTION,))
        self._last_selected: SpotifyCatalogItem | None = None

    @property
    def candidates(self) -> tuple[SpotifyCatalogItem, ...]:
        return self._candidates

    def replace(
        self,
        candidates: tuple[SpotifyCatalogItem, ...],
        *,
        allowed_action_ids: tuple[str, ...] = (SPOTIFY_PLAY_ALBUM_ACTION,),
    ) -> None:
        if len(candidates) > 5 or any(not _is_valid_album(item) for item in candidates):
            raise ValueError("album selections require at most five album items.")
        allowed = frozenset(allowed_action_ids)
        if not allowed or not allowed.issubset(
            {SPOTIFY_PLAY_ALBUM_ACTION, SPOTIFY_OPEN_ALBUM_ACTION}
        ):
            raise ValueError("album selections contain an unsupported follow-up.")
        self._candidates = tuple(candidates)
        self._allowed_action_ids = allowed
        self._last_selected = None

    def remember_selected(
        self,
        album_name: str,
        album_uri: str,
        album_artist: str = "",
    ) -> None:
        """Retain one validated album for an explicit contextual follow-up."""
        album = SpotifyCatalogItem(
            kind=SpotifyItemKind.ALBUM,
            spotify_id=album_uri.rsplit(":", 1)[-1],
            uri=album_uri,
            name=album_name,
            artist_names=(album_artist,) if album_artist else (),
        )
        if not _is_valid_album(album):
            raise ValueError("the selected Spotify album is invalid.")
        self._last_selected = album

    def clear_candidates(self) -> None:
        """Clear numbered results without discarding the last selected album."""
        self._candidates = ()
        self._allowed_action_ids = frozenset((SPOTIFY_PLAY_ALBUM_ACTION,))

    def clear(self) -> None:
        self.clear_candidates()
        self._last_selected = None

    def parse_follow_up(self, text: str) -> ActionRequest | None:
        normalized = text.strip()
        match = _ALBUM_RESULT_PATTERN.fullmatch(normalized)
        if match is None:
            context_match = _ALBUM_CONTEXT_PATTERN.fullmatch(normalized)
            if context_match is None or self._last_selected is None:
                return None
            action_id = {
                "play": SPOTIFY_PLAY_ALBUM_ACTION,
                "open": SPOTIFY_OPEN_ALBUM_ACTION,
            }[context_match.group("verb").casefold()]
            return _album_action_request(
                self._last_selected,
                action_id,
                source="spotify_context_followup",
                correlation_prefix="spotify-album-context",
            )

        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return None
        action_id = {
            "play": SPOTIFY_PLAY_ALBUM_ACTION,
            "open": SPOTIFY_OPEN_ALBUM_ACTION,
        }[match.group("verb").casefold()]
        if action_id not in self._allowed_action_ids:
            return None

        album = self._candidates[index - 1]
        return _album_action_request(
            album,
            action_id,
            source="spotify_followup",
            correlation_prefix="spotify-album-result",
        )

    def follow_up_error(self, text: str) -> str | None:
        """Explain a recognized result reference that cannot be fulfilled."""
        normalized = text.strip()
        context_match = _ALBUM_CONTEXT_PATTERN.fullmatch(normalized)
        if context_match is not None and self._last_selected is None:
            return (
                "There is no recent Spotify album to use. "
                "Search for or open an album first."
            )

        match = _ALBUM_RESULT_PATTERN.fullmatch(normalized)
        if match is None:
            return None
        if not self._candidates:
            return (
                "There are no active Spotify album results. Search for an album first."
            )
        index = _result_index(match)
        if index <= 0 or index > len(self._candidates):
            return f"Choose an album result from 1 to {len(self._candidates)}."
        action_id = {
            "play": SPOTIFY_PLAY_ALBUM_ACTION,
            "open": SPOTIFY_OPEN_ALBUM_ACTION,
        }[match.group("verb").casefold()]
        if action_id not in self._allowed_action_ids:
            allowed = (
                "opened"
                if SPOTIFY_OPEN_ALBUM_ACTION in self._allowed_action_ids
                else "played"
            )
            return f"Those album results can only be {allowed}."
        return None


def build_spotify_album_executors(
    client: SpotifyClient,
    device_coordinator: SpotifyDeviceCoordinator,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[
    SpotifyAlbumSearchExecutor
    | SpotifyAlbumOpenExecutor
    | SpotifyAlbumPlaybackExecutor,
    ...,
]:
    return (
        SpotifyAlbumSearchExecutor(client, preference_ranker),
        SpotifyAlbumOpenExecutor(client, preference_ranker=preference_ranker),
        SpotifyAlbumPlaybackExecutor(
            client,
            device_coordinator,
            preference_ranker,
        ),
    )


async def _resolve_album(
    client: SpotifyClient,
    action: ValidatedAction,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[SpotifyCatalogItem | None, tuple[SpotifyCatalogItem, ...]]:
    selected = _selected_album_from_action(action)
    if selected is not None:
        return selected, ()
    title, artist = _album_query(action)
    candidates = await _search_album_candidates(
        client,
        title,
        artist,
        preference_ranker,
    )
    return _select_album(title, artist, candidates), candidates


async def _search_album_candidates(
    client: SpotifyClient,
    title: str,
    artist: str,
    preference_ranker: SpotifyPreferenceRanker | None = None,
) -> tuple[SpotifyCatalogItem, ...]:
    query = f"album:{title}"
    if artist:
        query = f"{query} artist:{artist}"
    result = await asyncio.to_thread(
        client.search,
        query,
        kinds=(SpotifyItemKind.ALBUM,),
        limit_per_kind=5,
    )
    candidates = tuple(item for item in result.items if _is_valid_album(item))[:5]
    if candidates:
        return await _rank_candidates(preference_ranker, candidates)

    relaxed_query = " ".join(part for part in (title, artist) if part)
    result = await asyncio.to_thread(
        client.search,
        relaxed_query,
        kinds=(SpotifyItemKind.ALBUM,),
        limit_per_kind=5,
    )
    candidates = tuple(item for item in result.items if _is_valid_album(item))[:5]
    return await _rank_candidates(preference_ranker, candidates)


async def _rank_candidates(
    preference_ranker: SpotifyPreferenceRanker | None,
    candidates: tuple[SpotifyCatalogItem, ...],
) -> tuple[SpotifyCatalogItem, ...]:
    if preference_ranker is None:
        return candidates
    return await preference_ranker.rank(candidates)


def _album_query(action: ValidatedAction) -> tuple[str, str]:
    return (
        str(action.parameters["album_query"]),
        str(action.parameters.get("artist_query", "")),
    )


def _result_index(match: re.Match[str]) -> int:
    raw_index = match.group("index").casefold()
    return int(raw_index) if raw_index.isdigit() else _NUMBER_WORDS[raw_index]


def _album_action_request(
    album: SpotifyCatalogItem,
    action_id: str,
    *,
    source: str,
    correlation_prefix: str,
) -> ActionRequest:
    artist = album.artist_names[0] if album.artist_names else ""
    parameters = {
        "service": "spotify",
        "album_query": album.name,
        "album_name": album.name,
        "album_uri": album.uri,
    }
    if artist:
        parameters["artist_query"] = artist
        parameters["album_artist"] = artist
    return ActionRequest(
        correlation_id=f"{correlation_prefix}-{uuid4().hex}",
        action_id=action_id,
        source=source,
        parameters=parameters,
    )


def _selected_album_from_action(action: ValidatedAction) -> SpotifyCatalogItem | None:
    album_name = action.parameters.get("album_name")
    album_uri = action.parameters.get("album_uri")
    album_artist = action.parameters.get("album_artist", "")
    if album_name is None and album_uri is None:
        return None
    if not isinstance(album_name, str) or not isinstance(album_uri, str):
        return None
    if not isinstance(album_artist, str):
        return None
    if _ALBUM_URI_PATTERN.fullmatch(album_uri) is None:
        return None
    return SpotifyCatalogItem(
        kind=SpotifyItemKind.ALBUM,
        spotify_id=album_uri.rsplit(":", 1)[-1],
        uri=album_uri,
        name=album_name,
        artist_names=(album_artist,) if album_artist else (),
    )


def _select_album(
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


def _unresolved_album(
    action: ValidatedAction,
    candidates: tuple[SpotifyCatalogItem, ...],
) -> ActionExecutionResult:
    title, artist = _album_query(action)
    if not candidates:
        label = _query_label(title, artist)
        return _unavailable(f'I could not find a Spotify album matching "{label}".')
    return ActionExecutionResult(
        status=ActionStatus.FAILED,
        summary="I found several possible Spotify albums.",
        failure_category=ActionFailureCategory.TARGET_UNAVAILABLE,
        metadata={"album_candidates": candidates},
    )


def _text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, re.UNICODE))


def _is_valid_album(item: SpotifyCatalogItem) -> bool:
    return (
        item.kind is SpotifyItemKind.ALBUM
        and bool(item.name.strip())
        and _ALBUM_URI_PATTERN.fullmatch(item.uri) is not None
    )


def _query_label(title: str, artist: str) -> str:
    return f"{title} by {artist}" if artist else title


def _open_spotify_album_page(album_id: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9]{1,64}", album_id) is None:
        raise ValueError("Spotify album ID is invalid.")
    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        try:
            startfile(f"spotify:album:{album_id}")
            return True
        except OSError:
            pass
    return webbrowser.open(
        f"{_ALBUM_PAGE_URL_PREFIX}{album_id}",
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
        summary = "Spotify denied the album request. Check account access."
    elif error.status_code == 404:
        summary = (
            "Spotify found the album, but the playback device could not start it. "
            "Make Spotify active and try again."
        )
    elif error.status_code == 429:
        summary = "Spotify temporarily rate-limited album requests."
    else:
        summary = "The Spotify album request could not be completed."
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
        summary="Spotify album request was cancelled.",
    )
