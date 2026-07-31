"""Application-owned allowlist of assistant actions."""

from __future__ import annotations

from collections.abc import Iterable

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import (
    ActionDefinition,
    ActionFailureCategory,
    ActionParameterSpec,
    ActionRisk,
    ConfirmationPolicy,
    ParameterKind,
)

FILE_SEARCH_ACTION = "files.search"
DIRECTORY_SEARCH_ACTION = "directories.search"
OPEN_DIRECTORY_ACTION = "files.open_directory"
OPEN_FILE_ACTION = "files.open"
LAUNCH_APPLICATION_ACTION = "applications.launch"
CLOSE_APPLICATION_ACTION = "applications.close"

FILE_SEARCH_CAPABILITY = "files.search"
FILE_OPEN_CAPABILITY = "files.open"
APPLICATION_LAUNCH_CAPABILITY = "applications.launch"
APPLICATION_CLOSE_CAPABILITY = "applications.close"

ALLOWLISTED_APPLICATION_IDS = ("chrome", "discord", "spotify", "vlc", "vscode")


class ActionRegistry:
    """Resolve only action definitions registered by the application."""

    def __init__(self, definitions: Iterable[ActionDefinition]) -> None:
        entries: dict[str, ActionDefinition] = {}
        for definition in definitions:
            if definition.action_id in entries:
                raise ValueError(f"duplicate action definition: {definition.action_id}")
            entries[definition.action_id] = definition
        self._entries = entries

    @property
    def definitions(self) -> tuple[ActionDefinition, ...]:
        """Return registered definitions in stable insertion order."""
        return tuple(self._entries.values())

    def resolve(self, action_id: str) -> ActionDefinition:
        """Return one definition or reject the unknown identifier."""
        try:
            return self._entries[action_id]
        except KeyError as error:
            raise ActionValidationError(
                ActionFailureCategory.UNKNOWN_ACTION,
                "The requested assistant action is not registered.",
            ) from error


def build_default_action_registry() -> ActionRegistry:
    """Build the Phase 8 allowlist without enabling any executors."""
    return ActionRegistry(
        (
            ActionDefinition(
                action_id=FILE_SEARCH_ACTION,
                description="Search file names inside an approved directory.",
                risk=ActionRisk.READ_ONLY,
                permission_capability=FILE_SEARCH_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="file_search",
                target_parameter="root",
                parameters=(
                    ActionParameterSpec(
                        name="root",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                    ActionParameterSpec(
                        name="query",
                        kind=ParameterKind.STRING,
                        max_length=256,
                    ),
                    ActionParameterSpec(
                        name="media_only",
                        kind=ParameterKind.BOOLEAN,
                        required=False,
                    ),
                ),
                timeout_seconds=10,
                max_results=100,
            ),
            ActionDefinition(
                action_id=DIRECTORY_SEARCH_ACTION,
                description="Search directory names inside an approved root.",
                risk=ActionRisk.READ_ONLY,
                permission_capability=FILE_SEARCH_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="directory_search",
                target_parameter="root",
                parameters=(
                    ActionParameterSpec(
                        name="root",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                    ActionParameterSpec(
                        name="query",
                        kind=ParameterKind.STRING,
                        max_length=256,
                    ),
                    ActionParameterSpec(
                        name="match_all",
                        kind=ParameterKind.BOOLEAN,
                        required=False,
                    ),
                ),
                timeout_seconds=10,
                max_results=100,
            ),
            ActionDefinition(
                action_id=OPEN_DIRECTORY_ACTION,
                description="Open an approved directory in the file browser.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=FILE_OPEN_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="open_directory",
                target_parameter="path",
                parameters=(
                    ActionParameterSpec(
                        name="path",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                ),
                timeout_seconds=10,
            ),
            ActionDefinition(
                action_id=OPEN_FILE_ACTION,
                description="Open an allowlisted passive file after confirmation.",
                risk=ActionRisk.SENSITIVE_OPEN,
                permission_capability=FILE_OPEN_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.ALWAYS,
                executor_id="open_safe_file",
                target_parameter="path",
                parameters=(
                    ActionParameterSpec(
                        name="path",
                        kind=ParameterKind.STRING,
                        max_length=1024,
                    ),
                ),
                timeout_seconds=10,
            ),
            ActionDefinition(
                action_id=LAUNCH_APPLICATION_ACTION,
                description="Launch one explicitly enabled catalog application.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=APPLICATION_LAUNCH_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="launch_allowlisted_application",
                target_parameter="application_id",
                parameters=(
                    ActionParameterSpec(
                        name="application_id",
                        kind=ParameterKind.STRING,
                        max_length=64,
                        allowed_values=ALLOWLISTED_APPLICATION_IDS,
                    ),
                ),
                timeout_seconds=10,
            ),
            ActionDefinition(
                action_id=CLOSE_APPLICATION_ACTION,
                description="Gracefully close an explicitly enabled application.",
                risk=ActionRisk.USER_VISIBLE,
                permission_capability=APPLICATION_CLOSE_CAPABILITY,
                confirmation_policy=ConfirmationPolicy.NEVER,
                executor_id="close_allowlisted_application",
                target_parameter="application_id",
                parameters=(
                    ActionParameterSpec(
                        name="application_id",
                        kind=ParameterKind.STRING,
                        max_length=64,
                        allowed_values=ALLOWLISTED_APPLICATION_IDS,
                    ),
                ),
                timeout_seconds=10,
            ),
        )
    )
