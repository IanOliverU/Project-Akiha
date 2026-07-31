"""Capability- and target-specific assistant action permission policy."""

from __future__ import annotations

from collections.abc import Iterable

from project_akiha.core.actions.models import (
    ConfirmationPolicy,
    PermissionDecision,
    PermissionGrant,
    ValidatedAction,
)
from project_akiha.core.actions.path_policy import ProtectedPathPolicy
from project_akiha.core.actions.registry import (
    APPLICATION_CLOSE_CAPABILITY,
    APPLICATION_LAUNCH_CAPABILITY,
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
)

_FILE_CAPABILITIES = frozenset({FILE_SEARCH_CAPABILITY, FILE_OPEN_CAPABILITY})
_APPLICATION_CAPABILITIES = frozenset(
    {APPLICATION_LAUNCH_CAPABILITY, APPLICATION_CLOSE_CAPABILITY}
)


class ActionPermissionPolicy:
    """Authorize only requests covered by an active scoped grant."""

    def __init__(self, path_policy: ProtectedPathPolicy) -> None:
        self._path_policy = path_policy

    def evaluate(
        self,
        action: ValidatedAction,
        grants: Iterable[PermissionGrant],
        *,
        confirmed: bool = False,
    ) -> PermissionDecision:
        """Return the current permission decision without executing anything."""
        matching_grant = any(
            self._grant_matches(action, grant) for grant in grants if grant.is_active
        )
        if not matching_grant:
            return PermissionDecision.MISSING
        if (
            action.definition.confirmation_policy is ConfirmationPolicy.ALWAYS
            and not confirmed
        ):
            return PermissionDecision.CONFIRMATION_REQUIRED
        return PermissionDecision.GRANTED

    def _grant_matches(
        self,
        action: ValidatedAction,
        grant: PermissionGrant,
    ) -> bool:
        capability = action.definition.permission_capability
        if grant.capability != capability:
            return False
        if capability in _FILE_CAPABILITIES:
            return self._path_policy.is_within(
                action.normalized_target,
                grant.target,
            )
        if capability in _APPLICATION_CAPABILITIES:
            return grant.target.casefold() == action.normalized_target.casefold()
        return False
