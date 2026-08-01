"""Typed contracts for permission-gated assistant actions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_CORRELATION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class ActionRisk(StrEnum):
    """Risk classification owned by the action registry."""

    READ_ONLY = "read_only"
    USER_VISIBLE = "user_visible"
    SENSITIVE_OPEN = "sensitive_open"
    PROHIBITED = "prohibited"


class ConfirmationPolicy(StrEnum):
    """Whether an otherwise permitted action needs current user approval."""

    NEVER = "never"
    ALWAYS = "always"


class ParameterKind(StrEnum):
    """Supported primitive action-parameter kinds."""

    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"


class ActionStatus(StrEnum):
    """Bounded outcome states returned by the action service."""

    SUCCESS = "success"
    DENIED = "denied"
    CANCELLED = "cancelled"
    CONFIRMATION_REQUIRED = "confirmation_required"
    UNAVAILABLE = "unavailable"
    TIMED_OUT = "timed_out"
    FAILED = "failed"


class PermissionDecision(StrEnum):
    """Permission decision recorded for an evaluated action."""

    NOT_EVALUATED = "not_evaluated"
    MISSING = "missing"
    CONFIRMATION_REQUIRED = "confirmation_required"
    GRANTED = "granted"


class ActionFailureCategory(StrEnum):
    """Sanitized failure categories safe for diagnostics and audit."""

    UNKNOWN_ACTION = "unknown_action"
    INVALID_PARAMETERS = "invalid_parameters"
    INVALID_TARGET = "invalid_target"
    PERMISSION_REQUIRED = "permission_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    EXECUTOR_UNAVAILABLE = "executor_unavailable"
    TARGET_UNAVAILABLE = "target_unavailable"
    EXECUTION_FAILED = "execution_failed"


@dataclass(frozen=True, slots=True)
class ActionParameterSpec:
    """One typed parameter accepted by a registered action."""

    name: str
    kind: ParameterKind
    required: bool = True
    max_length: int | None = None
    allowed_values: tuple[str, ...] = ()
    minimum_value: int | None = None
    maximum_value: int | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.name, "parameter name")
        if self.max_length is not None and self.max_length <= 0:
            raise ValueError("parameter max_length must be greater than zero.")
        if self.allowed_values and self.kind is not ParameterKind.STRING:
            raise ValueError("allowed_values are supported only for string parameters.")
        if (
            self.minimum_value is not None or self.maximum_value is not None
        ) and self.kind is not ParameterKind.INTEGER:
            raise ValueError(
                "numeric bounds are supported only for integer parameters."
            )
        if (
            self.minimum_value is not None
            and self.maximum_value is not None
            and self.minimum_value > self.maximum_value
        ):
            raise ValueError("parameter minimum cannot exceed its maximum.")
        normalized_values = tuple(value.strip() for value in self.allowed_values)
        if any(not value for value in normalized_values):
            raise ValueError("parameter allowed_values cannot contain empty values.")
        if len(set(normalized_values)) != len(normalized_values):
            raise ValueError("parameter allowed_values cannot contain duplicates.")
        object.__setattr__(self, "allowed_values", normalized_values)


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """Application-owned schema and policy for one allowlisted action."""

    action_id: str
    description: str
    risk: ActionRisk
    permission_capability: str
    confirmation_policy: ConfirmationPolicy
    executor_id: str
    target_parameter: str
    parameters: tuple[ActionParameterSpec, ...]
    timeout_seconds: int
    max_results: int | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.action_id, "action identifier")
        _require_identifier(self.permission_capability, "permission capability")
        _require_identifier(self.executor_id, "executor identifier")
        _require_identifier(self.target_parameter, "target parameter")
        if not self.description.strip():
            raise ValueError("action description cannot be empty.")
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError("action timeout must be between 1 and 300 seconds.")
        if self.max_results is not None and self.max_results <= 0:
            raise ValueError("action max_results must be greater than zero.")

        names = tuple(parameter.name for parameter in self.parameters)
        if len(set(names)) != len(names):
            raise ValueError("action parameter names cannot contain duplicates.")
        if self.target_parameter not in names:
            raise ValueError(
                "action target_parameter must name a registered parameter."
            )


@dataclass(frozen=True, slots=True)
class ActionRequest:
    """Untrusted structured action proposal from chat or a direct UI surface."""

    correlation_id: str
    action_id: str
    source: str
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        if not _CORRELATION_PATTERN.fullmatch(self.correlation_id):
            raise ValueError("action correlation_id contains invalid characters.")
        _require_identifier(self.action_id, "action identifier")
        _require_identifier(self.source, "action source")
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(dict(self.parameters)),
        )


@dataclass(frozen=True, slots=True)
class ValidatedAction:
    """Registered action request after schema and target validation."""

    request: ActionRequest
    definition: ActionDefinition
    parameters: Mapping[str, object]
    normalized_target: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "parameters",
            MappingProxyType(dict(self.parameters)),
        )


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """One persisted capability- and target-specific permission."""

    id: int
    capability: str
    target: str
    created_at: str
    revoked_at: str | None = None

    @property
    def is_active(self) -> bool:
        """Return whether the permission remains usable."""
        return self.revoked_at is None


@dataclass(frozen=True, slots=True)
class ApprovedDirectory:
    """Aggregated active file permissions for one canonical directory root."""

    root: str
    search_permission_id: int | None
    open_permission_id: int | None
    is_available: bool

    def __post_init__(self) -> None:
        if not self.root.strip():
            raise ValueError("approved directory root cannot be empty.")
        permission_ids = (
            self.search_permission_id,
            self.open_permission_id,
        )
        if all(permission_id is None for permission_id in permission_ids):
            raise ValueError("approved directory needs at least one permission.")
        if any(
            permission_id is not None and permission_id <= 0
            for permission_id in permission_ids
        ):
            raise ValueError("approved directory permission ids must be positive.")

    @property
    def can_search(self) -> bool:
        """Return whether filename search is permitted for this root."""
        return self.search_permission_id is not None

    @property
    def can_open(self) -> bool:
        """Return whether directory and passive-file opening is permitted."""
        return self.open_permission_id is not None


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Sanitized result of evaluating or executing one action request."""

    correlation_id: str
    action_id: str
    status: ActionStatus
    summary: str
    permission_decision: PermissionDecision
    failure_category: ActionFailureCategory | None = None
    metadata: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@dataclass(frozen=True, slots=True)
class FileSearchMatch:
    """Bounded metadata for one regular file found by an approved search."""

    name: str
    path: str
    size_bytes: int
    modified_at: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("file search match name cannot be empty.")
        if not self.path.strip():
            raise ValueError("file search match path cannot be empty.")
        if self.size_bytes < 0:
            raise ValueError("file search match size cannot be negative.")


@dataclass(frozen=True, slots=True)
class DirectorySearchMatch:
    """Bounded metadata for one directory found under an approved root."""

    name: str
    path: str
    modified_at: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("directory search match name cannot be empty.")
        if not self.path.strip():
            raise ValueError("directory search match path cannot be empty.")


@dataclass(frozen=True, slots=True)
class ActionExecutionResult:
    """Sanitized executor outcome before the action service records an audit."""

    status: ActionStatus
    summary: str
    metadata: Mapping[str, object] = MappingProxyType({})
    failure_category: ActionFailureCategory | None = None

    def __post_init__(self) -> None:
        if self.status not in {
            ActionStatus.SUCCESS,
            ActionStatus.CANCELLED,
            ActionStatus.UNAVAILABLE,
            ActionStatus.TIMED_OUT,
            ActionStatus.FAILED,
        }:
            raise ValueError("executors can return only execution outcome statuses.")
        if not self.summary.strip():
            raise ValueError("execution result summary cannot be empty.")
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@dataclass(frozen=True, slots=True)
class ActionAuditEntry:
    """Persisted, sanitized record of an action evaluation."""

    id: int
    correlation_id: str
    action_id: str
    source: str
    normalized_target: str | None
    permission_decision: PermissionDecision
    result_status: ActionStatus
    duration_ms: int
    failure_category: ActionFailureCategory | None
    created_at: str


def _require_identifier(value: str, label: str) -> None:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{label} must be a lowercase dotted identifier.")
