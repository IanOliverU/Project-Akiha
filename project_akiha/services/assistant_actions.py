"""Fail-closed orchestration for Phase 8A assistant action evaluation."""

from __future__ import annotations

from collections.abc import Iterable
from time import monotonic

from project_akiha.core.actions import (
    ActionAuditRepository,
    ActionCancellationToken,
    ActionExecutionResult,
    ActionFailureCategory,
    ActionPermissionPolicy,
    ActionPermissionRepository,
    ActionRequest,
    ActionRequestValidator,
    ActionResult,
    ActionStatus,
    ActionValidationError,
    AssistantActionExecutor,
    PermissionDecision,
    ValidatedAction,
)


class AssistantActionService:
    """Validate, authorize, execute, and audit registered assistant actions."""

    def __init__(
        self,
        validator: ActionRequestValidator,
        permission_policy: ActionPermissionPolicy,
        permission_repository: ActionPermissionRepository,
        audit_repository: ActionAuditRepository,
        executors: Iterable[AssistantActionExecutor] = (),
    ) -> None:
        self._validator = validator
        self._permission_policy = permission_policy
        self._permission_repository = permission_repository
        self._audit_repository = audit_repository
        self._executors = {executor.executor_id: executor for executor in executors}

    async def evaluate_request(
        self,
        request: ActionRequest,
        *,
        confirmed: bool = False,
        cancellation_token: ActionCancellationToken | None = None,
    ) -> ActionResult:
        """Evaluate, execute if permitted, and audit a typed request."""
        if not isinstance(request, ActionRequest):
            raise TypeError("assistant actions require a typed ActionRequest.")
        if not isinstance(confirmed, bool):
            raise TypeError("assistant action confirmation must be boolean.")
        if cancellation_token is not None and not isinstance(
            cancellation_token,
            ActionCancellationToken,
        ):
            raise TypeError("assistant action cancellation must use a typed token.")

        started_at = monotonic()
        token = cancellation_token or ActionCancellationToken()
        normalized_target: str | None = None
        try:
            action = self._validator.validate(request)
            normalized_target = action.normalized_target
        except ActionValidationError as error:
            result = ActionResult(
                correlation_id=request.correlation_id,
                action_id=request.action_id,
                status=ActionStatus.DENIED,
                summary="Akiha refused an invalid assistant action request.",
                permission_decision=PermissionDecision.NOT_EVALUATED,
                failure_category=error.category,
            )
            await self._record_result(
                request,
                result,
                normalized_target=None,
                started_at=started_at,
            )
            return result

        grants = await self._permission_repository.get_active_permissions(
            action.definition.permission_capability
        )
        decision = self._permission_policy.evaluate(
            action,
            grants,
            confirmed=confirmed,
        )
        if decision is PermissionDecision.MISSING:
            result = ActionResult(
                correlation_id=request.correlation_id,
                action_id=request.action_id,
                status=ActionStatus.DENIED,
                summary="This assistant action needs a matching permission.",
                permission_decision=decision,
                failure_category=ActionFailureCategory.PERMISSION_REQUIRED,
            )
        elif decision is PermissionDecision.CONFIRMATION_REQUIRED:
            result = ActionResult(
                correlation_id=request.correlation_id,
                action_id=request.action_id,
                status=ActionStatus.CONFIRMATION_REQUIRED,
                summary="This assistant action needs current user confirmation.",
                permission_decision=decision,
                failure_category=ActionFailureCategory.CONFIRMATION_REQUIRED,
            )
        else:
            execution = await self._execute_or_refuse(action, token)
            result = ActionResult(
                correlation_id=request.correlation_id,
                action_id=request.action_id,
                status=execution.status,
                summary=execution.summary,
                permission_decision=decision,
                failure_category=execution.failure_category,
                metadata=execution.metadata,
            )

        await self._record_result(
            request,
            result,
            normalized_target=normalized_target,
            started_at=started_at,
        )
        return result

    async def _execute_or_refuse(
        self,
        action: ValidatedAction,
        cancellation_token: ActionCancellationToken,
    ) -> ActionExecutionResult:
        """Execute only the registered executor that owns this exact action."""
        executor = self._executors.get(action.definition.executor_id)
        if executor is None or executor.action_id != action.definition.action_id:
            return ActionExecutionResult(
                status=ActionStatus.UNAVAILABLE,
                summary="This assistant action is not enabled yet.",
                failure_category=ActionFailureCategory.EXECUTOR_UNAVAILABLE,
            )
        try:
            return await executor.execute(
                action,
                cancellation_token=cancellation_token,
            )
        except Exception:
            return ActionExecutionResult(
                status=ActionStatus.FAILED,
                summary="The assistant action could not be completed.",
                failure_category=ActionFailureCategory.EXECUTION_FAILED,
            )

    async def _record_result(
        self,
        request: ActionRequest,
        result: ActionResult,
        *,
        normalized_target: str | None,
        started_at: float,
    ) -> None:
        duration_ms = max(0, round((monotonic() - started_at) * 1000))
        await self._audit_repository.record_action_audit(
            correlation_id=request.correlation_id,
            action_id=request.action_id,
            source=request.source,
            normalized_target=normalized_target,
            permission_decision=result.permission_decision,
            result_status=result.status,
            duration_ms=duration_ms,
            failure_category=result.failure_category,
        )
