"""Framework-free, non-authorizing readiness and lease contracts."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import StrEnum

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import ActionRequest
from project_akiha.core.actions.registry import ActionRegistry
from project_akiha.core.actions.validation import _validate_parameters


class ActionClarificationReason(StrEnum):
    MISSING_TARGET = "missing_target"
    NO_MATCH = "no_match"
    MULTIPLE_MATCHES = "multiple_matches"
    MULTIPLE_ACTIONS = "multiple_actions"
    MISSING_PARAMETER = "missing_parameter"
    UNCERTAIN_TIME = "uncertain_time"


class ActionReadinessStatus(StrEnum):
    READY = "ready"
    CLARIFICATION_REQUIRED = "clarification_required"
    INVALID = "invalid"


class ClarificationOutcome(StrEnum):
    RESOLVED = "resolved"
    PENDING = "pending"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    STALE = "stale"
    INVALID = "invalid"
    SUPERSEDED = "superseded"


class ClarificationAnswerSource(StrEnum):
    LOCAL_UI = "local_ui"
    LOCAL_TEXT = "local_text"
    LOCAL_FINAL_TRANSCRIPT = "local_final_transcript"
    PROVIDER = "provider"


class LocalSearchOutcome(StrEnum):
    STALE = "stale"
    CLARIFICATION_REQUIRED = "clarification_required"
    READY_TO_EXECUTE = "ready_to_execute"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LocalSearchIdentity:
    """Immutable authority captured when a local search is accepted."""

    owner_epoch: int
    request_digest: str
    request_id: str
    action_id: str
    source: str
    operation: str
    generation: int
    nonce: str
    creation_id: str
    created_at: float
    deadline: float
    request: ActionRequest = field(repr=False)


@dataclass(frozen=True, slots=True)
class LocalSearchResolution:
    outcome: LocalSearchOutcome
    identity: LocalSearchIdentity
    request: ActionRequest | None = field(default=None, repr=False)


def request_fingerprint(request: ActionRequest) -> str:
    """Bind identity and normalized primitive arguments without retaining text."""
    parameters = {}
    for key, value in request.parameters.items():
        if not isinstance(key, str) or type(value) not in {str, int, bool}:
            raise ValueError("lease arguments must be primitive")
        if isinstance(value, str):
            if len(value) > 2048 or any(ord(char) < 32 for char in value):
                raise ValueError("lease argument is invalid")
            value = value.strip()
        parameters[key] = value
    payload = [request.correlation_id, request.action_id, request.source, parameters]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ActionClarificationSpec:
    reason: ActionClarificationReason
    missing_parameters: tuple[str, ...] = ()
    choice_count: int = 0
    cloud_origin: bool = False
    truncated: bool = False
    local_music_catalog: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.reason, ActionClarificationReason):
            raise TypeError("clarification reason must be typed")
        if not isinstance(self.missing_parameters, tuple) or any(
            not isinstance(name, str) or not name.isidentifier()
            for name in self.missing_parameters
        ):
            raise TypeError("missing parameter fields must be typed identifiers")
        if len(set(self.missing_parameters)) != len(self.missing_parameters):
            raise ValueError("duplicate missing parameters")
        if type(self.cloud_origin) is not bool or type(self.truncated) is not bool:
            raise TypeError("cloud origin must be boolean")
        # This is presentation metadata. Service admission still caps search/
        # provider candidates at 5/10; only the explicit local music catalog may
        # present the complete registered list (up to 1,000).
        if type(self.local_music_catalog) is not bool:
            raise TypeError("local music catalog provenance must be boolean")
        maximum = 1000 if self.local_music_catalog else 10
        if type(self.choice_count) is not int or not 0 <= self.choice_count <= maximum:
            raise ValueError("clarification choices must be bounded")


@dataclass(frozen=True, slots=True)
class ActionReadinessDecision:
    status: ActionReadinessStatus
    request: ActionRequest = field(repr=False)
    spec: ActionClarificationSpec | None = None


@dataclass(frozen=True, slots=True)
class ClarificationLeaseIdentity:
    lease_id: str
    nonce: str
    owner_epoch: int
    revision: int
    request_digest: str
    created_at: float
    deadline: float

    def __post_init__(self) -> None:
        if not self.lease_id or not self.nonce or len(self.request_digest) != 64:
            raise ValueError("invalid lease identity")
        if (
            type(self.revision) is not int
            or type(self.owner_epoch) is not int
            or self.revision < 0
            or self.owner_epoch < 0
        ):
            raise ValueError("invalid lease revision")
        if not all(math.isfinite(v) for v in (self.created_at, self.deadline)):
            raise ValueError("lease clock values must be finite")
        if self.deadline != self.created_at + 120.0:
            raise ValueError("clarification lifetime must be exactly 120 seconds")


@dataclass(frozen=True, slots=True)
class ClarificationAnswer:
    identity: ClarificationLeaseIdentity
    source: ClarificationAnswerSource
    value: str = field(default="", repr=False)
    choice_index: int | None = None
    cancel: bool = False
    open_any: bool = False
    choice_id: str | None = field(default=None, repr=False)
    artist_query: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ClarificationLeaseIdentity) or not isinstance(
            self.source, ClarificationAnswerSource
        ):
            raise TypeError("answer identity and provenance must be typed")
        if type(self.cancel) is not bool or type(self.open_any) is not bool:
            raise TypeError("answer flags must be boolean")
        if not isinstance(self.value, str) or not isinstance(self.artist_query, str):
            raise TypeError("answer must be local text")
        if self.choice_id is not None and (
            not isinstance(self.choice_id, str) or not 1 <= len(self.choice_id) <= 64
        ):
            raise ValueError("invalid local choice identity")


@dataclass(frozen=True, slots=True)
class LocalTargetChoices:
    """Trusted local catalog snapshots; no provider or persistence representation."""

    requests: tuple[ActionRequest, ...] = field(repr=False)
    labels: tuple[str, ...] = field(repr=False)
    empty_message: str
    truncated: bool = False
    enabled: tuple[bool, ...] = ()
    spotify_history: bool = False

    @property
    def choice_limit(self) -> int:
        return (
            1000
            if self.requests
            and all(
                isinstance(request, ActionRequest)
                and request.action_id == "files.open"
                and request.source == "chat.music"
                for request in self.requests
            )
            else 10
        )

    def __post_init__(self) -> None:
        if (
            not isinstance(self.requests, tuple)
            or not isinstance(self.labels, tuple)
            or len(self.requests) != len(self.labels)
            or len(self.requests) > self.choice_limit
            or any(not isinstance(r, ActionRequest) for r in self.requests)
            or any(
                not isinstance(label, str)
                or not 1 <= len(label) <= 128
                or any(ord(c) < 32 for c in label)
                for label in self.labels
            )
            or type(self.truncated) is not bool
            or not isinstance(self.enabled, tuple)
            or (self.enabled and len(self.enabled) != len(self.requests))
            or any(type(value) is not bool for value in self.enabled)
            or type(self.spotify_history) is not bool
        ):
            raise ValueError("invalid bounded local catalog choices")


@dataclass(frozen=True, slots=True)
class SpotifyHistoryIdentity:
    """One local fetch bound to the complete foreground lease and account."""

    lease: ClarificationLeaseIdentity
    nonce: str
    account_generation: int
    request: ActionRequest = field(repr=False)


@dataclass(frozen=True, slots=True)
class ClarificationResolution:
    outcome: ClarificationOutcome
    identity: ClarificationLeaseIdentity | None = None
    request: ActionRequest | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class ConfirmationLease:
    lease_id: str
    nonce: str
    owner_epoch: int
    request_digest: str
    created_at: float
    deadline: float
    request: ActionRequest = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not self.lease_id
            or not self.nonce
            or type(self.owner_epoch) is not int
            or self.owner_epoch < 0
        ):
            raise ValueError("invalid confirmation identity")
        if not all(math.isfinite(v) for v in (self.created_at, self.deadline)):
            raise ValueError("confirmation clock values must be finite")
        if self.deadline != self.created_at + 60.0:
            raise ValueError("confirmation lifetime must be exactly 60 seconds")
        if self.request_digest != request_fingerprint(self.request):
            raise ValueError("confirmation must bind exact request")


def analyze_action_readiness(
    request: ActionRequest, registry: ActionRegistry
) -> ActionReadinessDecision:
    """Distinguish missing registered fields from invalid input; never authorize."""
    try:
        request_fingerprint(request)
        definition = registry.resolve(request.action_id)
        empty_required = {
            spec.name
            for spec in definition.parameters
            if spec.required
            and isinstance(request.parameters.get(spec.name), str)
            and not request.parameters[spec.name].strip()
        }
        parameters = {
            name: value
            for name, value in request.parameters.items()
            if name not in empty_required
        }
        present_specs = tuple(
            spec for spec in definition.parameters if spec.name in parameters
        )
        _validate_parameters(parameters, present_specs)
        missing = tuple(
            spec.name
            for spec in definition.parameters
            if spec.required and spec.name not in parameters
        )
    except (ActionValidationError, ValueError, TypeError):
        return ActionReadinessDecision(ActionReadinessStatus.INVALID, request)
    if missing:
        reason = (
            ActionClarificationReason.MISSING_TARGET
            if definition.target_parameter in missing
            else ActionClarificationReason.MISSING_PARAMETER
        )
        return ActionReadinessDecision(
            ActionReadinessStatus.CLARIFICATION_REQUIRED,
            request,
            ActionClarificationSpec(reason, missing),
        )
    return ActionReadinessDecision(ActionReadinessStatus.READY, request)


def approved_directory_aliases(roots: tuple[str, ...]) -> dict[str, str]:
    """Reject colliding root names rather than silently choosing a directory."""
    from pathlib import PureWindowsPath

    aliases: dict[str, str] = {}
    for root in roots:
        alias = PureWindowsPath(root).name.casefold()
        if not alias:
            continue
        if alias in aliases and aliases[alias].casefold() != root.casefold():
            raise ValueError("approved directory aliases are ambiguous")
        aliases[alias] = root
    return aliases
