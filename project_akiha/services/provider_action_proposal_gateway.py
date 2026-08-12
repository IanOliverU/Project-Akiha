"""Convert owned provider tool proposals into untrusted Phase 8 requests."""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Protocol

from project_akiha.core.actions import (
    DIRECTORY_SEARCH_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
    ActionRequest,
    ActionValidationError,
    DirectorySearchMatch,
    FileSearchMatch,
    ProviderActionToolCatalog,
)
from project_akiha.core.actions.registry import (
    FILE_SEARCH_ACTION,
    SPOTIFY_PLAY_TRACK_ACTION,
    SPOTIFY_SEARCH_TRACKS_ACTION,
)
from project_akiha.core.voice_session import ActionProposal, ProposalState

_RESULT_REFERENCE_PATTERN = re.compile(r"result\s+(?P<index>[1-9]|10)", re.I)
_SPOTIFY_TRACK_URI_PATTERN = re.compile(r"spotify:track:[A-Za-z0-9]{1,64}\Z")
_MAX_LOCAL_RESULTS = 10


class ProposalTurnAuthority(Protocol):
    """Minimal active-turn authority required by the proposal gateway."""

    def accepts_callback(self, session_id: str, turn_id: str) -> bool:
        """Return whether the proposal still belongs to the active turn."""


class ProposalGatewayReason(StrEnum):
    """Privacy-safe outcome for one provider proposal conversion."""

    ACCEPTED = "accepted"
    STALE = "stale"
    DUPLICATE = "duplicate"
    NOT_READY = "not_ready"
    NOT_EXPOSED = "not_exposed"


@dataclass(frozen=True, slots=True)
class ProposalGatewayDecision:
    """Sanitized proposal decision retained without target arguments."""

    session_id: str
    turn_id: str
    proposal_id: str
    action_id: str
    accepted: bool
    reason: ProposalGatewayReason


@dataclass(frozen=True, slots=True)
class ProposalGatewayResult:
    """One decision and its transient untrusted request, when accepted."""

    decision: ProposalGatewayDecision
    request: ActionRequest | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.decision.accepted != (self.request is not None):
            raise ValueError("accepted proposal decisions require one action request.")
        if self.request is not None:
            if self.request.action_id != self.decision.action_id:
                raise ValueError("proposal decision and request action IDs must match.")
            if not self.request.source.startswith("provider."):
                raise ValueError("provider action requests require a provider source.")


class ProviderActionProposalGateway:
    """Reject stale or replayed proposals before Phase 8 validation."""

    def __init__(
        self,
        catalog: ProviderActionToolCatalog,
        turn_authority: ProposalTurnAuthority,
        *,
        max_records: int = 256,
        local_result_ttl_seconds: float = 300.0,
        monotonic_clock=monotonic,
    ) -> None:
        if max_records <= 0:
            raise ValueError("proposal gateway record bound must be positive.")
        if local_result_ttl_seconds <= 0:
            raise ValueError("local result TTL must be positive.")
        self._catalog = catalog
        self._turn_authority = turn_authority
        self._max_records = max_records
        self._lock = threading.RLock()
        self._consumed: OrderedDict[tuple[str, str, str], None] = OrderedDict()
        self._decisions: deque[ProposalGatewayDecision] = deque(maxlen=max_records)
        self._directory_aliases: dict[str, str] = {}
        self._file_result_paths: tuple[str, ...] = ()
        self._directory_result_paths: tuple[str, ...] = ()
        self._spotify_track_results: tuple[dict[str, str], ...] = ()
        self._local_result_ttl_seconds = local_result_ttl_seconds
        self._monotonic_clock = monotonic_clock
        self._local_results_expire_at = 0.0

    @property
    def decisions(self) -> tuple[ProposalGatewayDecision, ...]:
        """Return bounded sanitized history without proposal arguments."""
        with self._lock:
            return tuple(self._decisions)

    def convert(self, proposal: ActionProposal) -> ProposalGatewayResult:
        """Convert one active, ready, exposed proposal without executing it."""
        if not isinstance(proposal, ActionProposal):
            raise TypeError("provider tools require a typed ActionProposal.")

        if not self._turn_authority.accepts_callback(
            proposal.session_id,
            proposal.turn_id,
        ):
            return self._reject(proposal, ProposalGatewayReason.STALE)

        identity = (
            proposal.session_id,
            proposal.turn_id,
            proposal.proposal_id,
        )
        with self._lock:
            if identity in self._consumed:
                return self._reject_locked(
                    proposal,
                    ProposalGatewayReason.DUPLICATE,
                )
            self._consumed[identity] = None
            if len(self._consumed) > self._max_records:
                self._consumed.popitem(last=False)

            if proposal.state is not ProposalState.READY:
                return self._reject_locked(
                    proposal,
                    ProposalGatewayReason.NOT_READY,
                )
            try:
                schema = self._catalog.resolve(proposal.action_name)
            except ActionValidationError:
                return self._reject_locked(
                    proposal,
                    ProposalGatewayReason.NOT_EXPOSED,
                )

            request = ActionRequest(
                correlation_id=_correlation_id(proposal),
                action_id=schema.action_id,
                source=_provider_source(proposal.source),
                parameters=self._resolve_local_arguments(
                    schema.action_id,
                    proposal.arguments,
                ),
            )
            decision = _decision(
                proposal,
                accepted=True,
                reason=ProposalGatewayReason.ACCEPTED,
            )
            self._decisions.append(decision)
            return ProposalGatewayResult(decision=decision, request=request)

    def set_directory_aliases(self, aliases: dict[str, str]) -> None:
        """Replace approved display-name mappings without exposing them upstream."""
        normalized: dict[str, str] = {}
        for alias, path in aliases.items():
            key = _directory_alias_key(alias)
            if key and isinstance(path, str) and path.strip():
                normalized[key] = path.strip()
        with self._lock:
            self._directory_aliases = normalized

    def set_file_results(self, matches: tuple[FileSearchMatch, ...]) -> None:
        """Retain bounded opaque file selections without exposing paths upstream."""
        if any(not isinstance(match, FileSearchMatch) for match in matches):
            raise TypeError("provider file results require FileSearchMatch values.")
        with self._lock:
            self._file_result_paths = tuple(
                match.path for match in matches[:_MAX_LOCAL_RESULTS]
            )
            self._directory_result_paths = ()
            self._spotify_track_results = ()
            self._local_results_expire_at = self._result_expiry(matches)

    def set_directory_results(
        self,
        matches: tuple[DirectorySearchMatch, ...],
    ) -> None:
        """Retain bounded opaque directory selections for numbered follow-ups."""
        if any(not isinstance(match, DirectorySearchMatch) for match in matches):
            raise TypeError(
                "provider directory results require DirectorySearchMatch values."
            )
        with self._lock:
            self._directory_result_paths = tuple(
                match.path for match in matches[:_MAX_LOCAL_RESULTS]
            )
            self._file_result_paths = ()
            self._spotify_track_results = ()
            self._local_results_expire_at = self._result_expiry(matches)

    def set_spotify_track_results(
        self,
        results: tuple[dict[str, str], ...],
    ) -> None:
        """Retain bounded Spotify choices behind opaque result references."""
        normalized = tuple(_spotify_track_parameters(result) for result in results)
        with self._lock:
            self._spotify_track_results = normalized[:_MAX_LOCAL_RESULTS]
            self._file_result_paths = ()
            self._directory_result_paths = ()
            self._local_results_expire_at = self._result_expiry(normalized)

    def clear_local_results(self) -> None:
        """Expire numbered provider references without altering replay records."""
        with self._lock:
            self._file_result_paths = ()
            self._directory_result_paths = ()
            self._spotify_track_results = ()
            self._local_results_expire_at = 0.0

    def clear(self) -> None:
        """Discard replay and diagnostic state when its owner shuts down."""
        with self._lock:
            self._consumed.clear()
            self._decisions.clear()
            self._file_result_paths = ()
            self._directory_result_paths = ()
            self._spotify_track_results = ()
            self._local_results_expire_at = 0.0

    def _reject(
        self,
        proposal: ActionProposal,
        reason: ProposalGatewayReason,
    ) -> ProposalGatewayResult:
        with self._lock:
            return self._reject_locked(proposal, reason)

    def _reject_locked(
        self,
        proposal: ActionProposal,
        reason: ProposalGatewayReason,
    ) -> ProposalGatewayResult:
        decision = _decision(proposal, accepted=False, reason=reason)
        self._decisions.append(decision)
        return ProposalGatewayResult(decision=decision)

    def _resolve_local_arguments(
        self,
        action_id: str,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        resolved = dict(arguments)
        spotify_result = self._resolve_spotify_result_reference(action_id, resolved)
        if spotify_result is not None:
            return spotify_result
        if action_id in {SPOTIFY_PLAY_TRACK_ACTION, SPOTIFY_SEARCH_TRACKS_ACTION}:
            resolved = _normalize_spotify_track_arguments(resolved)
        target_name = {
            FILE_SEARCH_ACTION: "root",
            DIRECTORY_SEARCH_ACTION: "root",
            OPEN_DIRECTORY_ACTION: "path",
            OPEN_FILE_ACTION: "path",
        }.get(action_id)
        if target_name is None:
            return resolved
        candidate = resolved.get(target_name)
        if not isinstance(candidate, str):
            return resolved
        result_path = self._resolve_result_reference(action_id, candidate)
        if result_path is not None:
            resolved[target_name] = result_path
            return resolved
        local_path = _resolve_approved_path(
            candidate,
            self._directory_aliases,
            allow_descendant=True,
        )
        if local_path is not None:
            resolved[target_name] = local_path
        return resolved

    def _resolve_spotify_result_reference(
        self,
        action_id: str,
        arguments: dict[str, object],
    ) -> dict[str, object] | None:
        if action_id != SPOTIFY_PLAY_TRACK_ACTION:
            return None
        candidate = arguments.get("track_query")
        if not isinstance(candidate, str):
            return None
        match = _RESULT_REFERENCE_PATTERN.fullmatch(candidate.strip())
        if match is None:
            return None
        if self._expire_local_results_if_needed():
            return None
        index = int(match.group("index")) - 1
        if index < 0 or index >= len(self._spotify_track_results):
            return None
        return dict(self._spotify_track_results[index])

    def _resolve_result_reference(self, action_id: str, value: str) -> str | None:
        match = _RESULT_REFERENCE_PATTERN.fullmatch(value.strip())
        if match is None:
            return None
        if self._expire_local_results_if_needed():
            return None
        paths = (
            self._file_result_paths
            if action_id == OPEN_FILE_ACTION
            else (
                self._directory_result_paths
                if action_id == OPEN_DIRECTORY_ACTION
                else ()
            )
        )
        index = int(match.group("index")) - 1
        if index < 0 or index >= len(paths):
            return None
        return paths[index]

    def _expire_local_results_if_needed(self) -> bool:
        if self._local_results_expire_at > self._monotonic_clock():
            return False
        self._file_result_paths = ()
        self._directory_result_paths = ()
        self._spotify_track_results = ()
        self._local_results_expire_at = 0.0
        return True

    def _result_expiry(self, matches: tuple[object, ...]) -> float:
        return (
            self._monotonic_clock() + self._local_result_ttl_seconds if matches else 0.0
        )


def _decision(
    proposal: ActionProposal,
    *,
    accepted: bool,
    reason: ProposalGatewayReason,
) -> ProposalGatewayDecision:
    return ProposalGatewayDecision(
        session_id=proposal.session_id,
        turn_id=proposal.turn_id,
        proposal_id=proposal.proposal_id,
        action_id=proposal.action_name,
        accepted=accepted,
        reason=reason,
    )


def _correlation_id(proposal: ActionProposal) -> str:
    identity = (
        f"{proposal.session_id}\0{proposal.turn_id}\0{proposal.proposal_id}"
    ).encode()
    return f"provider-{hashlib.sha256(identity).hexdigest()[:32]}"


def _provider_source(source: str) -> str:
    candidate = f"provider.{source.lower().replace(':', '.')}"
    if len(candidate) <= 64:
        return candidate
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]
    return f"provider.{digest}"


def _directory_alias_key(value: str) -> str:
    normalized = re.sub(r"[\W_]+", " ", value.casefold()).strip()
    tokens = normalized.split()
    while tokens and tokens[-1] in {"directory", "folder"}:
        tokens.pop()
    return " ".join(tokens)


def _resolve_approved_path(
    value: str,
    aliases: dict[str, str],
    *,
    allow_descendant: bool,
) -> str | None:
    exact = aliases.get(_directory_alias_key(value))
    if exact is not None:
        return exact

    if not allow_descendant:
        return None
    normalized = value.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        return None
    parts = [part.strip() for part in normalized.split("/")]
    if len(parts) < 2 or any(not _safe_relative_part(part) for part in parts):
        return None
    root = aliases.get(_directory_alias_key(parts[0]))
    if root is None:
        return None
    return str(Path(root).joinpath(*parts[1:]))


def _normalize_spotify_track_arguments(
    arguments: dict[str, object],
) -> dict[str, object]:
    track = arguments.get("track_query")
    artist = arguments.get("artist_query")
    if not isinstance(track, str) or (isinstance(artist, str) and artist.strip()):
        return arguments
    normalized = track.strip().rstrip(".!?").strip()
    if "|" in normalized:
        title, candidate_artist = normalized.split("|", 1)
    else:
        parts = re.split(r"\s+by\s+", normalized, maxsplit=1, flags=re.IGNORECASE)
        if len(parts) != 2:
            return arguments
        title, candidate_artist = parts
    if not title.strip() or not candidate_artist.strip():
        return arguments
    resolved = dict(arguments)
    resolved["track_query"] = title.strip()
    resolved["artist_query"] = candidate_artist.strip()
    return resolved


def _spotify_track_parameters(parameters: dict[str, str]) -> dict[str, str]:
    allowed = {
        "service",
        "track_query",
        "artist_query",
        "track_name",
        "track_artist",
        "track_uri",
    }
    if set(parameters) - allowed:
        raise ValueError("Spotify result parameters contain unsupported fields.")
    if parameters.get("service") != "spotify":
        raise ValueError("Spotify result parameters require the Spotify service.")
    required = ("track_query", "track_name", "track_uri")
    if any(not isinstance(parameters.get(name), str) for name in required):
        raise TypeError("Spotify result parameters require string track fields.")
    normalized = {
        name: value.strip()
        for name, value in parameters.items()
        if isinstance(value, str) and value.strip()
    }
    if any(not normalized.get(name) for name in required):
        raise ValueError("Spotify result parameters require non-empty track fields.")
    if _SPOTIFY_TRACK_URI_PATTERN.fullmatch(normalized["track_uri"]) is None:
        raise ValueError("Spotify result parameters require a validated track URI.")
    if len(normalized["track_query"]) > 160 or len(normalized["track_name"]) > 160:
        raise ValueError("Spotify result track text exceeds the bounded length.")
    for name in ("artist_query", "track_artist"):
        if len(normalized.get(name, "")) > 160:
            raise ValueError("Spotify result artist text exceeds the bounded length.")
    return normalized


def _safe_relative_part(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and ":" not in value
