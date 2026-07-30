"""Typed management of scoped assistant-action permission grants."""

from __future__ import annotations

from pathlib import Path

from project_akiha.core.actions import (
    ALLOWLISTED_APPLICATION_IDS,
    APPLICATION_LAUNCH_CAPABILITY,
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
    ActionPermissionRepository,
    PermissionGrant,
    ProtectedPathPolicy,
)

_FILE_CAPABILITIES = frozenset({FILE_SEARCH_CAPABILITY, FILE_OPEN_CAPABILITY})


class AssistantPermissionService:
    """Create only known directory and application permission scopes."""

    def __init__(
        self,
        repository: ActionPermissionRepository,
        path_policy: ProtectedPathPolicy,
    ) -> None:
        self._repository = repository
        self._path_policy = path_policy

    async def grant_directory(
        self,
        capability: str,
        root: str | Path,
    ) -> PermissionGrant:
        """Grant one file capability for a validated local directory root."""
        if capability not in _FILE_CAPABILITIES:
            raise ValueError("unsupported directory permission capability.")
        canonical_root = self._path_policy.validate_path(str(root))
        if not canonical_root.is_dir():
            raise ValueError(
                "directory permission target must be an existing directory."
            )
        return await self._repository.grant_permission(
            capability,
            str(canonical_root),
        )

    async def grant_application(self, application_id: str) -> PermissionGrant:
        """Grant launch permission for one application catalog identifier."""
        normalized = application_id.strip().lower()
        if normalized not in ALLOWLISTED_APPLICATION_IDS:
            raise ValueError("application is not in the Phase 8 allowlist.")
        return await self._repository.grant_permission(
            APPLICATION_LAUNCH_CAPABILITY,
            normalized,
        )

    async def get_active_permissions(
        self,
        capability: str | None = None,
    ) -> tuple[PermissionGrant, ...]:
        """Return active permission grants."""
        return await self._repository.get_active_permissions(capability)

    async def revoke(self, permission_id: int) -> bool:
        """Revoke one permission grant."""
        return await self._repository.revoke_permission(permission_id)
