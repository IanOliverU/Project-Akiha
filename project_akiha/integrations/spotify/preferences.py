"""Ephemeral local Spotify preference ranking and favorite queues."""

from __future__ import annotations

import asyncio
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from project_akiha.integrations.spotify.auth import SpotifyOAuthError
from project_akiha.integrations.spotify.client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyClient,
    SpotifyItemKind,
)

_TRACK_URI_PATTERN = re.compile(r"spotify:track:[A-Za-z0-9]{1,64}\Z")
_PLAYLIST_URI_PATTERN = re.compile(r"spotify:playlist:[A-Za-z0-9]{1,64}\Z")


@dataclass(frozen=True, slots=True)
class SpotifyPreferenceSnapshot:
    """Bounded preference scores derived from the current Spotify account."""

    created_at: float
    liked_tracks: tuple[SpotifyCatalogItem, ...]
    favorite_tracks: tuple[SpotifyCatalogItem, ...]
    personal_playlists: tuple[SpotifyCatalogItem, ...]
    track_scores: dict[str, float]
    artist_scores: dict[str, float]
    album_scores: dict[str, float]
    playlist_scores: dict[str, float]

    def affinity(self, item: SpotifyCatalogItem) -> float:
        """Return a local score without mutating or exporting account data."""
        if item.kind is SpotifyItemKind.TRACK:
            values = [self.track_scores.get(item.uri, 0.0)]
            values.extend(
                self.artist_scores.get(_text_key(name), 0.0)
                for name in item.artist_names
            )
            if item.album_name:
                values.append(self.album_scores.get(_text_key(item.album_name), 0.0))
            return max(values, default=0.0)
        if item.kind is SpotifyItemKind.ARTIST:
            return self.artist_scores.get(_text_key(item.name), 0.0)
        if item.kind is SpotifyItemKind.ALBUM:
            values = [self.album_scores.get(_text_key(item.name), 0.0)]
            values.extend(
                self.artist_scores.get(_text_key(name), 0.0)
                for name in item.artist_names
            )
            return max(values, default=0.0)
        if item.kind is SpotifyItemKind.PLAYLIST:
            return max(
                self.playlist_scores.get(item.uri, 0.0),
                self.playlist_scores.get(_text_key(item.name), 0.0),
            )
        return 0.0


class SpotifyPreferenceRanker:
    """Build and cache a privacy-safe profile from bounded Spotify endpoints."""

    def __init__(
        self,
        client: SpotifyClient,
        *,
        cache_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 30 <= cache_seconds <= 3600:
            raise ValueError("Spotify preference cache must be 30 to 3600 seconds.")
        self._client = client
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshot: SpotifyPreferenceSnapshot | None = None

    async def rank(
        self,
        items: Iterable[SpotifyCatalogItem],
    ) -> tuple[SpotifyCatalogItem, ...]:
        """Apply a bounded tie-break boost while preserving search relevance."""
        candidates = tuple(items)
        if len(candidates) < 2:
            return candidates
        try:
            snapshot = await self.snapshot()
        except SpotifyAPIError:
            return candidates

        scored = []
        for index, item in enumerate(candidates):
            provider_relevance = 1.0 - (0.04 * index)
            preference_boost = 0.10 * snapshot.affinity(item)
            scored.append((provider_relevance + preference_boost, index, item))
        scored.sort(key=lambda entry: (-entry[0], entry[1]))
        return tuple(item for _score, _index, item in scored)

    async def favorite_tracks(self, mode: str) -> tuple[SpotifyCatalogItem, ...]:
        """Return a bounded validated queue for liked-only or blended playback."""
        snapshot = await self.snapshot()
        if mode == "liked":
            return snapshot.liked_tracks[:50]
        if mode == "mix":
            return snapshot.favorite_tracks[:50]
        raise ValueError("Unsupported Spotify favorite mode.")

    def is_preferred_cached(self, item: SpotifyCatalogItem) -> bool:
        """Identify favored visible results without starting an API request."""
        with self._lock:
            snapshot = self._snapshot
        return snapshot is not None and snapshot.affinity(item) >= 0.65

    def invalidate(self) -> None:
        """Discard account-derived data after settings or session changes."""
        with self._lock:
            self._snapshot = None

    async def snapshot(self) -> SpotifyPreferenceSnapshot:
        """Return a fresh bounded profile, tolerating unavailable optional sources."""
        now = self._clock()
        with self._lock:
            cached = self._snapshot
        if cached is not None and now - cached.created_at < self._cache_seconds:
            return cached

        sources = await asyncio.gather(
            asyncio.to_thread(self._client.get_saved_tracks, max_items=50),
            asyncio.to_thread(
                self._client.get_top_items,
                SpotifyItemKind.TRACK,
                time_range="short_term",
                limit=20,
            ),
            asyncio.to_thread(
                self._client.get_top_items,
                SpotifyItemKind.TRACK,
                time_range="medium_term",
                limit=20,
            ),
            asyncio.to_thread(
                self._client.get_top_items,
                SpotifyItemKind.TRACK,
                time_range="long_term",
                limit=20,
            ),
            asyncio.to_thread(self._client.get_recent_tracks, limit=20),
            asyncio.to_thread(self._client.get_playlists, max_items=100),
            return_exceptions=True,
        )
        successful = [source for source in sources if isinstance(source, tuple)]
        if not successful:
            first_error = next(
                (source for source in sources if isinstance(source, Exception)),
                None,
            )
            if isinstance(first_error, (SpotifyAPIError, SpotifyOAuthError)):
                raise first_error
            raise SpotifyAPIError("Spotify preference data is unavailable.")

        liked, short, medium, long, recent, playlists = tuple(
            source if isinstance(source, tuple) else () for source in sources
        )
        snapshot = _build_snapshot(
            created_at=now,
            liked=liked,
            short=short,
            medium=medium,
            long=long,
            recent=recent,
            playlists=playlists,
        )
        with self._lock:
            current = self._snapshot
            if current is None or current.created_at <= snapshot.created_at:
                self._snapshot = snapshot
                return snapshot
            return current


def _build_snapshot(
    *,
    created_at: float,
    liked: tuple[SpotifyCatalogItem, ...],
    short: tuple[SpotifyCatalogItem, ...],
    medium: tuple[SpotifyCatalogItem, ...],
    long: tuple[SpotifyCatalogItem, ...],
    recent: tuple[SpotifyCatalogItem, ...],
    playlists: tuple[SpotifyCatalogItem, ...],
) -> SpotifyPreferenceSnapshot:
    track_scores: dict[str, float] = {}
    artist_scores: dict[str, float] = {}
    album_scores: dict[str, float] = {}
    playlist_scores: dict[str, float] = {}

    weighted_sources = (
        (liked, 1.0, 0.004),
        (short, 0.92, 0.012),
        (medium, 0.84, 0.010),
        (long, 0.76, 0.008),
        (recent, 0.60, 0.012),
    )
    for tracks, base, decay in weighted_sources:
        for index, track in enumerate(tracks):
            if not _is_valid_track(track):
                continue
            score = max(0.25, base - (decay * index))
            _retain_max(track_scores, track.uri, score)
            for artist in track.artist_names:
                _retain_max(artist_scores, _text_key(artist), score * 0.92)
            if track.album_name:
                _retain_max(album_scores, _text_key(track.album_name), score * 0.84)

    valid_playlists = tuple(
        playlist for playlist in playlists if _is_valid_playlist(playlist)
    )
    for index, playlist in enumerate(valid_playlists):
        score = max(0.45, 0.88 - (0.004 * index))
        _retain_max(playlist_scores, playlist.uri, score)
        _retain_max(playlist_scores, _text_key(playlist.name), score)

    combined = _deduplicate_tracks((*liked, *short, *medium, *long, *recent))
    favorite_tracks = tuple(
        sorted(
            combined,
            key=lambda item: track_scores.get(item.uri, 0.0),
            reverse=True,
        )
    )
    return SpotifyPreferenceSnapshot(
        created_at=created_at,
        liked_tracks=_deduplicate_tracks(liked),
        favorite_tracks=favorite_tracks,
        personal_playlists=valid_playlists,
        track_scores=track_scores,
        artist_scores=artist_scores,
        album_scores=album_scores,
        playlist_scores=playlist_scores,
    )


def _deduplicate_tracks(
    tracks: Iterable[SpotifyCatalogItem],
) -> tuple[SpotifyCatalogItem, ...]:
    seen: set[str] = set()
    result: list[SpotifyCatalogItem] = []
    for track in tracks:
        if not _is_valid_track(track) or track.uri in seen:
            continue
        seen.add(track.uri)
        result.append(track)
    return tuple(result)


def _retain_max(scores: dict[str, float], key: str, value: float) -> None:
    if key:
        scores[key] = max(scores.get(key, 0.0), min(max(value, 0.0), 1.0))


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


def _is_valid_playlist(item: SpotifyCatalogItem) -> bool:
    return (
        item.kind is SpotifyItemKind.PLAYLIST
        and bool(item.name.strip())
        and _PLAYLIST_URI_PATTERN.fullmatch(item.uri) is not None
    )
