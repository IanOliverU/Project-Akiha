"""Short-lived local references for deterministic assistant follow-ups."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from uuid import uuid4

from project_akiha.core.actions import ActionRequest
from project_akiha.core.actions.registry import (
    ALLOWLISTED_APPLICATION_IDS,
    CLOSE_APPLICATION_ACTION,
    SPOTIFY_PAUSE_ACTION,
    SPOTIFY_RESUME_ACTION,
)
from project_akiha.services.command_envelope import (
    DeterministicCommandEnvelopeParser,
)
from project_akiha.services.spoken_text import strip_speech_echo_wrappers

_REFERENCE_PREFIX_PATTERN = re.compile(
    r"^(?:(?:okay|ok|alright|all\s+right|hey)\s*[,!.?]?\s*)?"
    r"(?:(?:(?:hello|hi)\s+)?(?:akiha|akia|akaya|aka['\u2019]?ya)"
    r"\s*[,!.:?]?\s*)?",
    re.IGNORECASE,
)
_RESULT_REFERENCE_PATTERN = re.compile(
    r"^(?P<verb>play|open)\s+"
    r"(?:(?:the\s+)?(?P<kind>track|song|album|artist|playlist|file|folder|"
    r"directory|media)\s+)?"
    r"(?:result\s+(?P<result_index>\d+|one|two|three|four|five)|"
    r"(?:the\s+)?(?P<ordinal>\d+|one|two|three|four|five|first|second|third|"
    r"fourth|fifth)(?:\s+(?:one|result))?)\s*[.!?]?$",
    re.IGNORECASE,
)
_SELECTED_MEDIA_PATTERN = re.compile(
    r"^(?P<verb>play|open)\s+(?:that|this|same|the\s+same)\s+"
    r"(?P<kind>album|playlist)(?:\s+on\s+spotify)?\s*[.!?]?$",
    re.IGNORECASE,
)
_SPOTIFY_PRONOUN_PATTERN = re.compile(
    r"^(?P<verb>pause|resume|continue)\s+(?:it|that|the\s+music|"
    r"the\s+playback)(?:\s+on\s+spotify)?\s*[.!?]?$",
    re.IGNORECASE,
)
_APPLICATION_PRONOUN_PATTERN = re.compile(
    r"^(?:close|quit|exit)\s+(?:it|that|the\s+app|the\s+application)\s*[.!?]?$",
    re.IGNORECASE,
)
_DIRECTORY_CHILD_PATTERN = re.compile(
    r"^open\s+(?:the\s+)?(?P<name>.*?)\s*(?:folder|directory)\s+"
    r"(?:inside|under|in)\s+(?:it|that|there)\s*[.!?]?$",
    re.IGNORECASE,
)
_INDEX_VALUES = {
    "one": 1,
    "first": 1,
    "two": 2,
    "second": 2,
    "three": 3,
    "third": 3,
    "four": 4,
    "fourth": 4,
    "five": 5,
    "fifth": 5,
}


class EphemeralSelectionKind(StrEnum):
    """Validated result categories that can own a numbered follow-up."""

    FILE = "file"
    DIRECTORY = "directory"
    SPOTIFY_TRACK = "spotify_track"
    SPOTIFY_ALBUM = "spotify_album"
    SPOTIFY_ARTIST = "spotify_artist"
    SPOTIFY_PLAYLIST = "spotify_playlist"


_KIND_ALIASES = {
    "track": EphemeralSelectionKind.SPOTIFY_TRACK,
    "song": EphemeralSelectionKind.SPOTIFY_TRACK,
    "album": EphemeralSelectionKind.SPOTIFY_ALBUM,
    "artist": EphemeralSelectionKind.SPOTIFY_ARTIST,
    "playlist": EphemeralSelectionKind.SPOTIFY_PLAYLIST,
    "file": EphemeralSelectionKind.FILE,
    "media": EphemeralSelectionKind.FILE,
    "folder": EphemeralSelectionKind.DIRECTORY,
    "directory": EphemeralSelectionKind.DIRECTORY,
}


@dataclass(frozen=True, slots=True)
class EphemeralSelectionReference:
    """Reference to one item still owned by an existing validated store."""

    kind: EphemeralSelectionKind
    verb: str
    index: int | None = None
    selected: bool = False


@dataclass(frozen=True, slots=True)
class EphemeralDirectoryReference:
    """Request to search for one child beneath the recent approved directory."""

    directory_name: str
    parent_path: str


@dataclass(frozen=True, slots=True)
class EphemeralReferenceError:
    """Privacy-safe explanation for a recognized but unresolved reference."""

    message: str


EphemeralReferenceResolution = (
    ActionRequest
    | EphemeralSelectionReference
    | EphemeralDirectoryReference
    | EphemeralReferenceError
)


@dataclass(frozen=True, slots=True)
class _SelectionState:
    kind: EphemeralSelectionKind
    count: int
    allowed_verbs: frozenset[str]
    expires_at: float


@dataclass(frozen=True, slots=True)
class _SelectedState:
    kind: EphemeralSelectionKind
    allowed_verbs: frozenset[str]
    expires_at: float


class EphemeralActionContext:
    """Resolve bounded pronouns and result references without durable memory."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 300.0,
        now: Callable[[], float] = monotonic,
        envelope_parser: DeterministicCommandEnvelopeParser | None = None,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ephemeral context TTL must be positive.")
        self._ttl_seconds = ttl_seconds
        self._now = now
        self._envelope_parser = envelope_parser or DeterministicCommandEnvelopeParser()
        self.clear()

    @property
    def current_directory(self) -> str | None:
        """Return the recent approved directory while its reference is fresh."""
        if self._directory_path and self._directory_expires_at > self._now():
            return self._directory_path
        self._directory_path = ""
        self._directory_expires_at = 0.0
        return None

    def record_selection(
        self,
        kind: EphemeralSelectionKind,
        count: int,
        *,
        allowed_verbs: frozenset[str],
    ) -> None:
        """Make one bounded result set the only active numbered context."""
        if count < 0 or count > 10:
            raise ValueError("ephemeral result count must be between zero and ten.")
        if not allowed_verbs or not allowed_verbs.issubset({"open", "play"}):
            raise ValueError("ephemeral result verbs must be open or play.")
        self._selected = None
        if count == 0:
            self._selection = None
            return
        self._selection = _SelectionState(
            kind=kind,
            count=count,
            allowed_verbs=allowed_verbs,
            expires_at=self._expires_at(),
        )

    def clear_selection(self) -> None:
        self._selection = None

    def record_selected(
        self,
        kind: EphemeralSelectionKind,
        *,
        allowed_verbs: frozenset[str],
    ) -> None:
        """Remember only the type of one validated album or playlist."""
        if kind not in {
            EphemeralSelectionKind.SPOTIFY_ALBUM,
            EphemeralSelectionKind.SPOTIFY_PLAYLIST,
        }:
            raise ValueError("only albums and playlists support selected references.")
        if not allowed_verbs or not allowed_verbs.issubset({"open", "play"}):
            raise ValueError("selected reference verbs must be open or play.")
        self._selection = None
        self._selected = _SelectedState(
            kind=kind,
            allowed_verbs=allowed_verbs,
            expires_at=self._expires_at(),
        )

    def record_directory(self, path: str) -> None:
        normalized = path.strip()
        if not normalized or len(normalized) > 1_024:
            raise ValueError("ephemeral directory path is invalid.")
        self._directory_path = normalized
        self._directory_expires_at = self._expires_at()

    def record_application(self, application_id: str) -> None:
        normalized = application_id.strip().casefold()
        if normalized not in ALLOWLISTED_APPLICATION_IDS:
            raise ValueError("ephemeral application must be allowlisted.")
        self._application_id = normalized
        self._application_expires_at = self._expires_at()

    def clear_application(self, application_id: str | None = None) -> None:
        if application_id is None or self._application_id == application_id.casefold():
            self._application_id = ""
            self._application_expires_at = 0.0

    def record_spotify_activity(self) -> None:
        self._spotify_expires_at = self._expires_at()

    def resolve(self, text: str) -> EphemeralReferenceResolution | None:
        """Resolve one explicit local reference, never arbitrary conversation."""
        normalized = self._normalize(text)
        if not normalized:
            return None

        result_match = _RESULT_REFERENCE_PATTERN.fullmatch(normalized)
        if result_match is not None:
            return self._resolve_result(result_match)

        selected_match = _SELECTED_MEDIA_PATTERN.fullmatch(normalized)
        if selected_match is not None:
            return self._resolve_selected(selected_match)

        spotify_match = _SPOTIFY_PRONOUN_PATTERN.fullmatch(normalized)
        if spotify_match is not None:
            if self._spotify_expires_at <= self._now():
                self._spotify_expires_at = 0.0
                return EphemeralReferenceError(
                    "There is no recent Spotify playback to control."
                )
            verb = spotify_match.group("verb").casefold()
            action_id = (
                SPOTIFY_PAUSE_ACTION if verb == "pause" else SPOTIFY_RESUME_ACTION
            )
            return self._request(action_id, {"service": "spotify"})

        if _APPLICATION_PRONOUN_PATTERN.fullmatch(normalized) is not None:
            if not self._application_id or self._application_expires_at <= self._now():
                self.clear_application()
                return EphemeralReferenceError(
                    "There is no recent application to close."
                )
            return self._request(
                CLOSE_APPLICATION_ACTION,
                {"application_id": self._application_id},
            )

        directory_match = _DIRECTORY_CHILD_PATTERN.fullmatch(normalized)
        if directory_match is not None:
            parent_path = self.current_directory
            if parent_path is None:
                return EphemeralReferenceError(
                    "There is no recent approved directory to search inside."
                )
            directory_name = directory_match.group("name").strip()
            if not directory_name:
                return EphemeralReferenceError(
                    "Please name the folder you want to open inside it."
                )
            return EphemeralDirectoryReference(directory_name, parent_path)
        return None

    def clear(self) -> None:
        """Discard every transient reference without touching durable memory."""
        self._selection: _SelectionState | None = None
        self._selected: _SelectedState | None = None
        self._directory_path = ""
        self._directory_expires_at = 0.0
        self._application_id = ""
        self._application_expires_at = 0.0
        self._spotify_expires_at = 0.0

    def _resolve_result(
        self,
        match: re.Match[str],
    ) -> EphemeralSelectionReference | EphemeralReferenceError:
        selection = self._selection
        if selection is None or selection.expires_at <= self._now():
            self._selection = None
            return EphemeralReferenceError(
                "There are no active recent results. Search again first."
            )
        stated_kind = match.group("kind")
        if (
            stated_kind is not None
            and _KIND_ALIASES[stated_kind.casefold()] != selection.kind
        ):
            return EphemeralReferenceError(
                f"The active results are {self._kind_label(selection.kind)} results."
            )
        verb = match.group("verb").casefold()
        if verb not in selection.allowed_verbs:
            allowed = " or ".join(sorted(selection.allowed_verbs))
            return EphemeralReferenceError(
                f"Those results can only be used with {allowed}."
            )
        raw_index = match.group("result_index") or match.group("ordinal")
        index = (
            int(raw_index)
            if raw_index.isdigit()
            else _INDEX_VALUES[raw_index.casefold()]
        )
        if index <= 0 or index > selection.count:
            return EphemeralReferenceError(
                f"Choose a result from 1 to {selection.count}."
            )
        return EphemeralSelectionReference(selection.kind, verb, index=index)

    def _resolve_selected(
        self,
        match: re.Match[str],
    ) -> EphemeralSelectionReference | EphemeralReferenceError:
        selected = self._selected
        if selected is None or selected.expires_at <= self._now():
            self._selected = None
            return EphemeralReferenceError(
                "There is no recent Spotify album or playlist to use."
            )
        stated_kind = _KIND_ALIASES[match.group("kind").casefold()]
        if stated_kind != selected.kind:
            return EphemeralReferenceError(
                f"The recent Spotify item is a {self._kind_label(selected.kind)}."
            )
        verb = match.group("verb").casefold()
        if verb not in selected.allowed_verbs:
            allowed = " or ".join(sorted(selected.allowed_verbs))
            return EphemeralReferenceError(
                f"That item can only be used with {allowed}."
            )
        return EphemeralSelectionReference(selected.kind, verb, selected=True)

    def _normalize(self, text: str) -> str:
        normalized = strip_speech_echo_wrappers(text)
        normalized = _REFERENCE_PREFIX_PATTERN.sub("", normalized, count=1).strip()
        analysis = self._envelope_parser.analyze(normalized)
        if analysis.rejection is not None or analysis.envelope is None:
            return ""
        return analysis.envelope.command_text

    def _expires_at(self) -> float:
        return self._now() + self._ttl_seconds

    @staticmethod
    def _request(action_id: str, parameters: dict[str, object]) -> ActionRequest:
        return ActionRequest(
            correlation_id=f"ephemeral-reference-{uuid4().hex}",
            action_id=action_id,
            source="ephemeral_context",
            parameters=parameters,
        )

    @staticmethod
    def _kind_label(kind: EphemeralSelectionKind) -> str:
        return {
            EphemeralSelectionKind.FILE: "file",
            EphemeralSelectionKind.DIRECTORY: "directory",
            EphemeralSelectionKind.SPOTIFY_TRACK: "track",
            EphemeralSelectionKind.SPOTIFY_ALBUM: "album",
            EphemeralSelectionKind.SPOTIFY_ARTIST: "artist",
            EphemeralSelectionKind.SPOTIFY_PLAYLIST: "playlist",
        }[kind]
