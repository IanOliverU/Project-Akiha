"""Typed management of scoped assistant-action permission grants."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path

from project_akiha.core.actions import (
    ALLOWLISTED_APPLICATION_IDS,
    APPLICATION_CLOSE_CAPABILITY,
    APPLICATION_LAUNCH_CAPABILITY,
    FILE_OPEN_CAPABILITY,
    FILE_SEARCH_CAPABILITY,
    ActionPermissionRepository,
    ApprovedDirectory,
    PermissionGrant,
    ProtectedPathPolicy,
)

_FILE_CAPABILITIES = frozenset({FILE_SEARCH_CAPABILITY, FILE_OPEN_CAPABILITY})
_APPLICATION_CAPABILITIES = frozenset(
    {APPLICATION_LAUNCH_CAPABILITY, APPLICATION_CLOSE_CAPABILITY}
)


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

    async def grant_application(
        self,
        application_id: str,
        capability: str = APPLICATION_LAUNCH_CAPABILITY,
    ) -> PermissionGrant:
        """Grant one app capability for an application catalog identifier."""
        normalized = application_id.strip().lower()
        if normalized not in ALLOWLISTED_APPLICATION_IDS:
            raise ValueError("application is not in the Phase 8 allowlist.")
        if capability not in _APPLICATION_CAPABILITIES:
            raise ValueError("unsupported application permission capability.")
        return await self._repository.grant_permission(
            capability,
            normalized,
        )

    async def revoke_application(
        self,
        application_id: str,
        capability: str = APPLICATION_LAUNCH_CAPABILITY,
    ) -> bool:
        """Revoke one app capability for an application catalog identifier."""
        normalized = application_id.strip().lower()
        if normalized not in ALLOWLISTED_APPLICATION_IDS:
            raise ValueError("application is not in the Phase 8 allowlist.")
        if capability not in _APPLICATION_CAPABILITIES:
            raise ValueError("unsupported application permission capability.")
        grants = await self._repository.get_active_permissions(capability)
        revoked = False
        for grant in grants:
            if grant.target.casefold() == normalized:
                revoked = await self._repository.revoke_permission(grant.id) or revoked
        return revoked

    async def reset_all_permissions(self) -> int:
        """Revoke every active assistant-action grant."""
        grants = await self._repository.get_active_permissions()
        revoked_count = 0
        for grant in grants:
            if await self._repository.revoke_permission(grant.id):
                revoked_count += 1
        return revoked_count

    async def approve_directory(
        self,
        root: str | Path,
        *,
        allow_search: bool = True,
        allow_open: bool = False,
    ) -> ApprovedDirectory:
        """Create or atomically update one approved directory."""
        if not isinstance(allow_search, bool) or not isinstance(allow_open, bool):
            raise TypeError("approved directory flags must be boolean.")
        if not allow_search and not allow_open:
            raise ValueError("approved directory needs at least one capability.")

        canonical_root = self._validated_directory(root)
        stored_target = await self._existing_directory_target(canonical_root)
        grants = await self._repository.set_directory_permissions(
            stored_target,
            allow_search=allow_search,
            allow_open=allow_open,
        )
        return self._approved_directory(stored_target, grants)

    async def get_approved_directories(self) -> tuple[ApprovedDirectory, ...]:
        """Return active directory scopes aggregated by canonical target."""
        grants = await self._repository.get_active_permissions()
        grouped: dict[str, list[PermissionGrant]] = defaultdict(list)
        display_targets: dict[str, str] = {}
        for grant in grants:
            if grant.capability not in _FILE_CAPABILITIES:
                continue
            key = _path_key(grant.target)
            grouped[key].append(grant)
            display_targets.setdefault(key, grant.target)

        directories = tuple(
            self._approved_directory(display_targets[key], tuple(grouped[key]))
            for key in sorted(
                grouped, key=lambda item: display_targets[item].casefold()
            )
        )
        return directories

    async def remove_approved_directory(self, root: str | Path) -> bool:
        """Revoke all file permissions for a listed directory, including stale roots."""
        candidate_key = _path_key(str(root).strip())
        if not candidate_key:
            raise ValueError("approved directory root cannot be empty.")

        grants = await self._repository.get_active_permissions()
        stored_targets = tuple(
            dict.fromkeys(
                grant.target
                for grant in grants
                if grant.capability in _FILE_CAPABILITIES
                and _path_key(grant.target) == candidate_key
            )
        )
        if not stored_targets:
            return False
        revoked_count = 0
        for stored_target in stored_targets:
            revoked_count += await self._repository.revoke_directory_permissions(
                stored_target
            )
        return revoked_count > 0

    async def get_active_permissions(
        self,
        capability: str | None = None,
    ) -> tuple[PermissionGrant, ...]:
        """Return active permission grants."""
        return await self._repository.get_active_permissions(capability)

    async def revoke(self, permission_id: int) -> bool:
        """Revoke one permission grant."""
        return await self._repository.revoke_permission(permission_id)

    def _validated_directory(self, root: str | Path) -> Path:
        canonical_root = self._path_policy.validate_path(str(root))
        if not canonical_root.is_dir():
            raise ValueError(
                "directory permission target must be an existing directory."
            )
        return canonical_root

    async def _existing_directory_target(self, root: Path) -> str:
        candidate = str(root)
        candidate_key = _path_key(candidate)
        grants = await self._repository.get_active_permissions()
        return next(
            (
                grant.target
                for grant in grants
                if grant.capability in _FILE_CAPABILITIES
                and _path_key(grant.target) == candidate_key
            ),
            candidate,
        )

    def _approved_directory(
        self,
        target: str,
        grants: tuple[PermissionGrant, ...],
    ) -> ApprovedDirectory:
        search_id = next(
            (
                grant.id
                for grant in grants
                if grant.capability == FILE_SEARCH_CAPABILITY and grant.is_active
            ),
            None,
        )
        open_id = next(
            (
                grant.id
                for grant in grants
                if grant.capability == FILE_OPEN_CAPABILITY and grant.is_active
            ),
            None,
        )
        return ApprovedDirectory(
            root=target,
            search_permission_id=search_id,
            open_permission_id=open_id,
            is_available=self._directory_is_available(target),
        )

    def _directory_is_available(self, target: str) -> bool:
        try:
            path = self._path_policy.validate_path(target)
        except ValueError:
            return False
        return path.is_dir()


def _path_key(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    return os.path.normcase(os.path.abspath(normalized))
