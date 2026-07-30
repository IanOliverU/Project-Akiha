"""Framework-free contracts and policy for safe assistant actions."""

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.executors import (
    ActionCancellationToken,
    AssistantActionExecutor,
    FileSearchExecutor,
)
from project_akiha.core.actions.models import (
    ActionAuditEntry,
    ActionDefinition,
    ActionExecutionResult,
    ActionFailureCategory,
    ActionParameterSpec,
    ActionRequest,
    ActionResult,
    ActionRisk,
    ActionStatus,
    ApprovedDirectory,
    ConfirmationPolicy,
    FileSearchMatch,
    ParameterKind,
    PermissionDecision,
    PermissionGrant,
    ValidatedAction,
)
from project_akiha.core.actions.path_policy import ProtectedPathPolicy
from project_akiha.core.actions.permissions import ActionPermissionPolicy
from project_akiha.core.actions.registry import (
    ALLOWLISTED_APPLICATION_IDS,
    APPLICATION_LAUNCH_CAPABILITY,
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
    LAUNCH_APPLICATION_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
    ActionRegistry,
    build_default_action_registry,
)
from project_akiha.core.actions.repository import (
    ActionAuditRepository,
    ActionPermissionRepository,
)
from project_akiha.core.actions.validation import ActionRequestValidator

__all__ = [
    "ALLOWLISTED_APPLICATION_IDS",
    "APPLICATION_LAUNCH_CAPABILITY",
    "ApprovedDirectory",
    "ActionCancellationToken",
    "ActionAuditEntry",
    "ActionAuditRepository",
    "ActionDefinition",
    "ActionExecutionResult",
    "ActionFailureCategory",
    "ActionParameterSpec",
    "ActionPermissionPolicy",
    "ActionPermissionRepository",
    "ActionRegistry",
    "ActionRequest",
    "ActionRequestValidator",
    "ActionResult",
    "ActionRisk",
    "ActionStatus",
    "ActionValidationError",
    "AssistantActionExecutor",
    "ConfirmationPolicy",
    "FILE_OPEN_CAPABILITY",
    "FILE_SEARCH_CAPABILITY",
    "FileSearchExecutor",
    "FileSearchMatch",
    "LAUNCH_APPLICATION_ACTION",
    "OPEN_DIRECTORY_ACTION",
    "OPEN_FILE_ACTION",
    "ParameterKind",
    "PermissionDecision",
    "PermissionGrant",
    "ProtectedPathPolicy",
    "ValidatedAction",
    "build_default_action_registry",
]
