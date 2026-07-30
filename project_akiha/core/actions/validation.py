"""Schema and target validation for untrusted assistant action requests."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from project_akiha.core.actions.errors import ActionValidationError
from project_akiha.core.actions.models import (
    ActionFailureCategory,
    ActionParameterSpec,
    ActionRequest,
    ParameterKind,
    ValidatedAction,
)
from project_akiha.core.actions.passive_files import PassiveFilePolicy
from project_akiha.core.actions.path_policy import ProtectedPathPolicy
from project_akiha.core.actions.registry import (
    FILE_SEARCH_ACTION,
    OPEN_DIRECTORY_ACTION,
    OPEN_FILE_ACTION,
    ActionRegistry,
)

_FILE_ACTION_IDS = frozenset(
    {
        FILE_SEARCH_ACTION,
        OPEN_DIRECTORY_ACTION,
        OPEN_FILE_ACTION,
    }
)


class ActionRequestValidator:
    """Validate a request without performing or authorizing its action."""

    def __init__(
        self,
        registry: ActionRegistry,
        path_policy: ProtectedPathPolicy,
        passive_file_policy: PassiveFilePolicy | None = None,
    ) -> None:
        self._registry = registry
        self._path_policy = path_policy
        self._passive_file_policy = passive_file_policy or PassiveFilePolicy()

    def validate(self, request: ActionRequest) -> ValidatedAction:
        """Return a normalized registered request or raise a safe rejection."""
        if not isinstance(request, ActionRequest):
            raise TypeError("assistant actions require a typed ActionRequest.")

        definition = self._registry.resolve(request.action_id)
        normalized_parameters = _validate_parameters(
            request.parameters,
            definition.parameters,
        )
        raw_target = normalized_parameters[definition.target_parameter]
        if not isinstance(raw_target, str):
            raise _invalid_parameters("The action target must be a string.")

        if definition.action_id in _FILE_ACTION_IDS:
            normalized_target = str(self._path_policy.validate_path(raw_target))
            if definition.action_id == OPEN_FILE_ACTION:
                self._passive_file_policy.validate_file(Path(normalized_target))
            normalized_parameters[definition.target_parameter] = normalized_target
        else:
            normalized_target = raw_target

        return ValidatedAction(
            request=request,
            definition=definition,
            parameters=normalized_parameters,
            normalized_target=normalized_target,
        )


def _validate_parameters(
    values: Mapping[str, object],
    specs: tuple[ActionParameterSpec, ...],
) -> dict[str, object]:
    expected = {spec.name: spec for spec in specs}
    unexpected = set(values) - set(expected)
    if unexpected:
        raise _invalid_parameters("The action contains unexpected parameters.")

    normalized: dict[str, object] = {}
    for spec in specs:
        if spec.name not in values:
            if spec.required:
                raise _invalid_parameters("The action is missing required parameters.")
            continue
        normalized[spec.name] = _validate_parameter(values[spec.name], spec)
    return normalized


def _validate_parameter(value: object, spec: ActionParameterSpec) -> object:
    if spec.kind is ParameterKind.STRING:
        if not isinstance(value, str):
            raise _invalid_parameters(f"{spec.name} must be a string.")
        normalized = value.strip()
        if not normalized:
            raise _invalid_parameters(f"{spec.name} cannot be empty.")
        if spec.max_length is not None and len(normalized) > spec.max_length:
            raise _invalid_parameters(f"{spec.name} is too long.")
        if spec.allowed_values and normalized not in spec.allowed_values:
            raise _invalid_parameters(f"{spec.name} is not allowlisted.")
        return normalized

    if spec.kind is ParameterKind.INTEGER:
        if not isinstance(value, int) or isinstance(value, bool):
            raise _invalid_parameters(f"{spec.name} must be an integer.")
        return value

    if spec.kind is ParameterKind.BOOLEAN:
        if not isinstance(value, bool):
            raise _invalid_parameters(f"{spec.name} must be a boolean.")
        return value

    raise _invalid_parameters(f"{spec.name} uses an unsupported parameter kind.")


def _invalid_parameters(message: str) -> ActionValidationError:
    return ActionValidationError(ActionFailureCategory.INVALID_PARAMETERS, message)
