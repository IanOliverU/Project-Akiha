"""Framework-free product and safety contracts for Phase 13 utilities."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_MAXIMUM_RESULT_METADATA = 16
_MAXIMUM_RESULT_TEXT = 320
_MAXIMUM_METADATA_TEXT = 256


class UtilityOperation(StrEnum):
    """Closed operation IDs reserved for the approved Phase 13 scope."""

    TIMER_CREATE = "timers.create"
    TIMER_LIST = "timers.list"
    TIMER_CANCEL = "timers.cancel"
    TIMER_SNOOZE = "timers.snooze"
    REMINDER_CREATE = "reminders.create"
    REMINDER_LIST = "reminders.list"
    REMINDER_CANCEL = "reminders.cancel"
    REMINDER_SNOOZE = "reminders.snooze"
    WEATHER_CURRENT = "information.weather.current"
    WEATHER_FORECAST = "information.weather.forecast"
    NAVIGATION_SEARCH = "directories.search"
    NAVIGATION_OPEN = "files.open_directory"
    EXPORT_CONVERSATIONS = "exports.conversations"
    EXPORT_MEMORIES = "exports.memories"


class UtilityOwner(StrEnum):
    """Single service boundary allowed to implement an operation."""

    SCHEDULE_SERVICE = "schedule_service"
    CURRENT_INFORMATION_PROVIDER = "current_information_provider"
    APPROVED_NAVIGATION = "approved_navigation"
    EXPORT_SERVICE = "export_service"


class UtilityEffect(StrEnum):
    """Maximum side effect permitted by an operation contract."""

    READ_ONLY = "read_only"
    USER_VISIBLE = "user_visible"
    LOCAL_SCHEDULE = "local_schedule"
    USER_SELECTED_FILE_WRITE = "user_selected_file_write"


class UtilityAuthorization(StrEnum):
    """Authorization source required before an operation can run."""

    REQUEST_BOUND = "request_bound"
    SCOPED_GRANT = "scoped_grant"
    CONFIRM_EACH_TIME = "confirm_each_time"


class UtilityNetworkAccess(StrEnum):
    """Whether an operation may contact an external read-only provider."""

    NONE = "none"
    READ_ONLY = "read_only"


class UtilityStorage(StrEnum):
    """Maximum durable storage surface owned by an operation."""

    NONE = "none"
    SCHEDULE_METADATA = "schedule_metadata"
    USER_SELECTED_EXPORT = "user_selected_export"


class UtilityResultStatus(StrEnum):
    """Bounded internal outcomes returned by a utility service adapter."""

    SUCCESS = "success"
    CLARIFICATION_REQUIRED = "clarification_required"
    CONFIRMATION_REQUIRED = "confirmation_required"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"
    CANCELLED = "cancelled"
    FAILED = "failed"


class UtilityReasonCode(StrEnum):
    """Privacy-safe reason codes shared by diagnostics and action adapters."""

    COMPLETED = "completed"
    AMBIGUOUS = "ambiguous"
    MISSING_PARAMETER = "missing_parameter"
    INVALID_TIME = "invalid_time"
    CONFIRMATION_REQUIRED = "confirmation_required"
    PERMISSION_REQUIRED = "permission_required"
    OUTSIDE_APPROVED_ROOT = "outside_approved_root"
    EXPIRED = "expired"
    DUPLICATE = "duplicate"
    NOT_FOUND = "not_found"
    NETWORK_FAILURE = "network_failure"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    EXPORT_FAILED = "export_failed"
    CANCELLED = "cancelled"
    INTERNAL_FAILURE = "internal_failure"


_ALLOWED_REASONS = {
    UtilityResultStatus.SUCCESS: frozenset({UtilityReasonCode.COMPLETED}),
    UtilityResultStatus.CLARIFICATION_REQUIRED: frozenset(
        {
            UtilityReasonCode.AMBIGUOUS,
            UtilityReasonCode.MISSING_PARAMETER,
            UtilityReasonCode.INVALID_TIME,
        }
    ),
    UtilityResultStatus.CONFIRMATION_REQUIRED: frozenset(
        {UtilityReasonCode.CONFIRMATION_REQUIRED}
    ),
    UtilityResultStatus.DENIED: frozenset(
        {
            UtilityReasonCode.PERMISSION_REQUIRED,
            UtilityReasonCode.OUTSIDE_APPROVED_ROOT,
            UtilityReasonCode.EXPIRED,
            UtilityReasonCode.DUPLICATE,
        }
    ),
    UtilityResultStatus.UNAVAILABLE: frozenset(
        {
            UtilityReasonCode.NETWORK_FAILURE,
            UtilityReasonCode.PROVIDER_UNAVAILABLE,
            UtilityReasonCode.NOT_FOUND,
        }
    ),
    UtilityResultStatus.CANCELLED: frozenset({UtilityReasonCode.CANCELLED}),
    UtilityResultStatus.FAILED: frozenset(
        {
            UtilityReasonCode.EXPORT_FAILED,
            UtilityReasonCode.INTERNAL_FAILURE,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class UtilityOperationContract:
    """Non-executable ownership and safety declaration for one operation."""

    operation: UtilityOperation
    owner: UtilityOwner
    effect: UtilityEffect
    authorization: UtilityAuthorization
    network_access: UtilityNetworkAccess
    storage: UtilityStorage
    requires_approved_root: bool = False
    may_schedule_notification: bool = False

    def __post_init__(self) -> None:
        if _IDENTIFIER.fullmatch(self.operation.value) is None:
            raise ValueError("Utility operation must be a dotted identifier.")
        if (
            self.network_access is UtilityNetworkAccess.READ_ONLY
            and self.effect is not UtilityEffect.READ_ONLY
        ):
            raise ValueError("Network-enabled utilities must remain read-only.")
        if self.requires_approved_root and (
            self.authorization is not UtilityAuthorization.SCOPED_GRANT
            or self.network_access is not UtilityNetworkAccess.NONE
        ):
            raise ValueError(
                "Approved-root utilities require a scoped local-only grant."
            )
        if self.effect is UtilityEffect.USER_SELECTED_FILE_WRITE and (
            self.authorization is not UtilityAuthorization.CONFIRM_EACH_TIME
            or self.storage is not UtilityStorage.USER_SELECTED_EXPORT
            or self.network_access is not UtilityNetworkAccess.NONE
        ):
            raise ValueError(
                "Export writes require current confirmation and local export storage."
            )
        if self.storage is UtilityStorage.SCHEDULE_METADATA and (
            self.owner is not UtilityOwner.SCHEDULE_SERVICE
            or self.effect
            not in {UtilityEffect.READ_ONLY, UtilityEffect.LOCAL_SCHEDULE}
        ):
            raise ValueError(
                "Schedule metadata may be accessed only by the schedule service."
            )
        if self.may_schedule_notification and (
            self.owner is not UtilityOwner.SCHEDULE_SERVICE
            or self.storage is not UtilityStorage.SCHEDULE_METADATA
        ):
            raise ValueError(
                "Only persisted schedule operations may schedule notifications."
            )

    @property
    def action_id(self) -> str:
        """Return the existing action-registry identifier for this operation."""
        return self.operation.value


@dataclass(frozen=True, slots=True)
class UtilityResult:
    """Sanitized internal utility outcome before action/event presentation."""

    correlation_id: str
    operation: UtilityOperation
    status: UtilityResultStatus
    reason: UtilityReasonCode
    summary: str
    metadata: Mapping[str, str | int | float | bool | None] = MappingProxyType({})

    def __post_init__(self) -> None:
        if _CORRELATION_ID.fullmatch(self.correlation_id) is None:
            raise ValueError("Utility correlation ID contains invalid characters.")
        if self.reason not in _ALLOWED_REASONS[self.status]:
            raise ValueError("Utility result reason does not match its status.")
        summary = self.summary.strip()
        if not summary or len(summary) > _MAXIMUM_RESULT_TEXT or "\x00" in summary:
            raise ValueError("Utility result summary is empty or exceeds its bound.")
        metadata = dict(self.metadata)
        if len(metadata) > _MAXIMUM_RESULT_METADATA:
            raise ValueError("Utility result metadata exceeds its field bound.")
        for key, value in metadata.items():
            if _IDENTIFIER.fullmatch(key) is None:
                raise ValueError("Utility result metadata key is invalid.")
            if not isinstance(value, (str, int, float, bool, type(None))):
                raise TypeError("Utility result metadata values must be scalar.")
            if isinstance(value, str) and len(value) > _MAXIMUM_METADATA_TEXT:
                raise ValueError("Utility result metadata text exceeds its bound.")
        object.__setattr__(self, "summary", summary)
        object.__setattr__(self, "metadata", MappingProxyType(metadata))


class UtilityContractCatalog:
    """Resolve approved declarations without exposing or executing an action."""

    def __init__(self, contracts: Iterable[UtilityOperationContract]) -> None:
        entries: dict[UtilityOperation, UtilityOperationContract] = {}
        action_ids: set[str] = set()
        for contract in contracts:
            if contract.operation in entries or contract.action_id in action_ids:
                raise ValueError("Duplicate utility operation contract.")
            entries[contract.operation] = contract
            action_ids.add(contract.action_id)
        self._entries = entries

    @property
    def contracts(self) -> tuple[UtilityOperationContract, ...]:
        """Return declarations in stable insertion order."""
        return tuple(self._entries.values())

    def resolve(self, operation: UtilityOperation) -> UtilityOperationContract:
        """Resolve one typed operation or reject it as outside Phase 13."""
        if not isinstance(operation, UtilityOperation):
            raise TypeError("Utility contracts require a typed operation.")
        try:
            return self._entries[operation]
        except KeyError as error:
            raise ValueError("Utility operation is not approved.") from error

    def resolve_action(self, action_id: str) -> UtilityOperationContract:
        """Resolve a future action ID without making it executable."""
        try:
            operation = UtilityOperation(action_id)
        except ValueError as error:
            raise ValueError("Utility action is not approved.") from error
        return self.resolve(operation)


def build_phase_13_utility_catalog() -> UtilityContractCatalog:
    """Build the approved, non-executable Phase 13 operation catalog."""
    schedule_read = {
        "owner": UtilityOwner.SCHEDULE_SERVICE,
        "effect": UtilityEffect.READ_ONLY,
        "authorization": UtilityAuthorization.REQUEST_BOUND,
        "network_access": UtilityNetworkAccess.NONE,
        "storage": UtilityStorage.SCHEDULE_METADATA,
    }
    schedule_write = {
        **schedule_read,
        "effect": UtilityEffect.LOCAL_SCHEDULE,
    }
    contracts = (
        UtilityOperationContract(
            UtilityOperation.TIMER_CREATE,
            **schedule_write,
            may_schedule_notification=True,
        ),
        UtilityOperationContract(UtilityOperation.TIMER_LIST, **schedule_read),
        UtilityOperationContract(UtilityOperation.TIMER_CANCEL, **schedule_write),
        UtilityOperationContract(
            UtilityOperation.TIMER_SNOOZE,
            **schedule_write,
            may_schedule_notification=True,
        ),
        UtilityOperationContract(
            UtilityOperation.REMINDER_CREATE,
            **schedule_write,
            may_schedule_notification=True,
        ),
        UtilityOperationContract(UtilityOperation.REMINDER_LIST, **schedule_read),
        UtilityOperationContract(
            UtilityOperation.REMINDER_CANCEL,
            **schedule_write,
        ),
        UtilityOperationContract(
            UtilityOperation.REMINDER_SNOOZE,
            **schedule_write,
            may_schedule_notification=True,
        ),
        *(
            UtilityOperationContract(
                operation,
                owner=UtilityOwner.CURRENT_INFORMATION_PROVIDER,
                effect=UtilityEffect.READ_ONLY,
                authorization=UtilityAuthorization.REQUEST_BOUND,
                network_access=UtilityNetworkAccess.READ_ONLY,
                storage=UtilityStorage.NONE,
            )
            for operation in (
                UtilityOperation.WEATHER_CURRENT,
                UtilityOperation.WEATHER_FORECAST,
            )
        ),
        UtilityOperationContract(
            UtilityOperation.NAVIGATION_SEARCH,
            owner=UtilityOwner.APPROVED_NAVIGATION,
            effect=UtilityEffect.READ_ONLY,
            authorization=UtilityAuthorization.SCOPED_GRANT,
            network_access=UtilityNetworkAccess.NONE,
            storage=UtilityStorage.NONE,
            requires_approved_root=True,
        ),
        UtilityOperationContract(
            UtilityOperation.NAVIGATION_OPEN,
            owner=UtilityOwner.APPROVED_NAVIGATION,
            effect=UtilityEffect.USER_VISIBLE,
            authorization=UtilityAuthorization.SCOPED_GRANT,
            network_access=UtilityNetworkAccess.NONE,
            storage=UtilityStorage.NONE,
            requires_approved_root=True,
        ),
        *(
            UtilityOperationContract(
                operation,
                owner=UtilityOwner.EXPORT_SERVICE,
                effect=UtilityEffect.USER_SELECTED_FILE_WRITE,
                authorization=UtilityAuthorization.CONFIRM_EACH_TIME,
                network_access=UtilityNetworkAccess.NONE,
                storage=UtilityStorage.USER_SELECTED_EXPORT,
            )
            for operation in (
                UtilityOperation.EXPORT_CONVERSATIONS,
                UtilityOperation.EXPORT_MEMORIES,
            )
        ),
    )
    return UtilityContractCatalog(contracts)
