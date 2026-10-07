"""Transient account history for an explicit local target picker, never search."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from project_akiha.core.actions.clarification import LocalTargetChoices
from project_akiha.core.actions.models import ActionRequest
from project_akiha.integrations.spotify.auth import SpotifyOAuthError
from project_akiha.integrations.spotify.client import (
    SpotifyAPIError,
    SpotifyCatalogItem,
    SpotifyClient,
    SpotifyItemKind,
)
from project_akiha.integrations.spotify.session import SpotifySession

HISTORY_FETCH_LIMIT = 20
HISTORY_PICKER_LIMIT = 10
HISTORY_SCOPE = "user-read-recently-played"


class HistoryStatus(StrEnum):
    READY = "ready"
    EMPTY = "empty"
    MISSING_SCOPE = "missing_scope"
    DISCONNECTED = "disconnected"
    RATE_LIMITED = "rate_limited"
    FAILED = "failed"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class SpotifyHistorySnapshot:
    status: HistoryStatus
    tracks: tuple[SpotifyCatalogItem, ...] = field(default=(), repr=False)

    @property
    def message(self) -> str:
        return {
            HistoryStatus.READY: "Choose an available recently played entry.",
            HistoryStatus.EMPTY: (
                "No recent Spotify plays were returned. Search for a song instead."
            ),
            HistoryStatus.MISSING_SCOPE: (
                "Spotify history permission is missing. Reconnect Spotify in Settings "
                "with user-read-recently-played permission, "
                "or search for a song instead."
            ),
            HistoryStatus.DISCONNECTED: (
                "Connect Spotify in Settings, or search for a song instead."
            ),
            HistoryStatus.RATE_LIMITED: (
                "Spotify rate limited history. Try again later, "
                "or search for a song instead."
            ),
            HistoryStatus.FAILED: (
                "Spotify history is unavailable. Try again later, "
                "or search for a song instead."
            ),
            HistoryStatus.STALE: (
                "This Spotify account changed. Issue the action again."
            ),
        }[self.status]


def fetch_spotify_history(
    client: SpotifyClient,
    session: SpotifySession,
    generation: int,
) -> SpotifyHistorySnapshot:
    """One bounded HTTP request after checking the existing token's granted scope."""
    try:
        if session.generation != generation:
            return SpotifyHistorySnapshot(HistoryStatus.STALE)
        if not session.has_scope(HISTORY_SCOPE):
            return SpotifyHistorySnapshot(HistoryStatus.MISSING_SCOPE)
        if session.generation != generation:
            return SpotifyHistorySnapshot(HistoryStatus.STALE)
        # Preserve newest-first API order, taking each track URI only once.
        # Scan only the latest 20 plays; never replace history with search.
        seen = set()
        unique = []
        for track in client.get_recent_tracks(limit=HISTORY_FETCH_LIMIT)[
            :HISTORY_FETCH_LIMIT
        ]:
            if track.uri in seen:
                continue
            seen.add(track.uri)
            unique.append(track)
            if len(unique) == HISTORY_PICKER_LIMIT:
                break
        tracks = tuple(unique)
        if session.generation != generation:
            return SpotifyHistorySnapshot(HistoryStatus.STALE)
        return SpotifyHistorySnapshot(
            HistoryStatus.READY if tracks else HistoryStatus.EMPTY, tracks
        )
    except SpotifyOAuthError:
        return SpotifyHistorySnapshot(HistoryStatus.DISCONNECTED)
    except SpotifyAPIError as error:
        status = {
            403: HistoryStatus.MISSING_SCOPE,
            401: HistoryStatus.DISCONNECTED,
            429: HistoryStatus.RATE_LIMITED,
        }.get(error.status_code, HistoryStatus.FAILED)
        return SpotifyHistorySnapshot(status)
    except Exception:
        # Never propagate exception text or history listings to logs/notifications.
        return SpotifyHistorySnapshot(HistoryStatus.FAILED)


def history_choices(
    request: ActionRequest, snapshot: SpotifyHistorySnapshot
) -> LocalTargetChoices:
    """Private direct-track requests, each with a request-bound opaque choice ID."""
    choices = []
    labels = []
    enabled = []
    for track in snapshot.tracks[:HISTORY_PICKER_LIMIT]:
        artist = track.artist_names[0] if track.artist_names else ""
        if (
            track.kind is not SpotifyItemKind.TRACK
            or re.fullmatch(r"spotify:track:[A-Za-z0-9]{1,64}", track.uri) is None
            or not track.name.strip()
            or len(track.name) > 160
            or len(artist) > 160
            or any(ord(c) < 32 for c in track.name + artist)
        ):
            return LocalTargetChoices(
                (),
                (),
                SpotifyHistorySnapshot(HistoryStatus.FAILED).message,
                spotify_history=True,
            )
        parameters = {
            "service": "spotify",
            "track_query": track.name,
            "track_name": track.name,
            "track_uri": track.uri,
        }
        if artist.strip():
            parameters.update(track_artist=artist, artist_query=artist)
        choices.append(
            ActionRequest(
                request.correlation_id,
                request.action_id,
                request.source,
                parameters,
            )
        )
        labels.append(
            (track.name + (" — " + artist if artist else ""))[:108]
            + (" (unavailable)" if not track.is_playable else "")
        )
        enabled.append(track.is_playable)
    return LocalTargetChoices(
        tuple(choices),
        tuple(labels),
        (
            snapshot.message
            if not choices
            else "These recent entries are unavailable. Search for a song instead."
        ),
        enabled=tuple(enabled),
        spotify_history=True,
    )
