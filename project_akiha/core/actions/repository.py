"""Persistence protocols for assistant permissions and action audit."""

from __future__ import annotations

from typing import Protocol

from project_akiha.core.actions.models import (
    ActionAuditEntry,
    ActionFailureCategory,
    ActionStatus,
    PermissionDecision,
    PermissionGrant,
)


class ActionPermissionRepository(Protocol):
    """Persist scoped assistant-action permissions."""

    async def grant_permission(
        self,
        capability: str,
        target: str,
    ) -> PermissionGrant:
        """Create or return one active permission."""

    async def get_active_permissions(
        self,
        capability: str | None = None,
    ) -> tuple[PermissionGrant, ...]:
        """Return active grants, optionally filtered by capability."""

    async def revoke_permission(self, permission_id: int) -> bool:
        """Revoke one active grant and report whether it changed."""

    async def set_directory_permissions(
        self,
        target: str,
        *,
        allow_search: bool,
        allow_open: bool,
    ) -> tuple[PermissionGrant, ...]:
        """Atomically replace active file permissions for one directory."""

    async def revoke_directory_permissions(self, target: str) -> int:
        """Atomically revoke all active file permissions for one directory."""


class ActionAuditRepository(Protocol):
    """Persist sanitized action evaluation history."""

    async def record_action_audit(
        self,
        *,
        correlation_id: str,
        action_id: str,
        source: str,
        normalized_target: str | None,
        permission_decision: PermissionDecision,
        result_status: ActionStatus,
        duration_ms: int,
        failure_category: ActionFailureCategory | None,
    ) -> ActionAuditEntry:
        """Persist one sanitized action evaluation."""

    async def get_recent_action_audits(
        self,
        limit: int,
    ) -> tuple[ActionAuditEntry, ...]:
        """Return recent action audits ordered newest first."""

    async def clear_action_audits(self) -> int:
        """Delete persisted sanitized action history and return its row count."""
