"""Clarification returns to real validation/grants/confirmation/execution."""

import asyncio
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.app.action_clarification_controller import (
    ActionClarificationController,
)
from project_akiha.core.actions import (
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    OpenFileExecutor,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.core.actions.clarification import (
    ClarificationAnswer,
    ClarificationAnswerSource,
    ClarificationOutcome,
)
from project_akiha.database import SQLiteActionRepository
from project_akiha.services.action_clarification import ActionClarificationService
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService


class Phase13BPermissionIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / "private-song.mp3"
        self.target.write_bytes(b"passive fixture")
        self.repository = SQLiteActionRepository(self.root / "test.sqlite3")
        self.policy = ProtectedPathPolicy()
        registry = build_default_action_registry()
        self.leases = ActionClarificationService(registry)
        self.controller = ActionClarificationController(self.leases)
        self.permissions = AssistantPermissionService(
            self.repository, self.policy, on_change=self.controller.invalidate
        )
        self.opened = []
        self.service = AssistantActionService(
            ActionRequestValidator(registry, self.policy),
            ActionPermissionPolicy(self.policy),
            self.repository,
            self.repository,
            executors=(OpenFileExecutor(self.opened.append),),
        )
        self.request = ActionRequest("open-request", "files.open", "chat", {})

    def resolve(self):
        self.controller.prepare(self.request)
        pending = self.leases.pending
        result = self.controller.resolve(
            ClarificationAnswer(
                pending.identity,
                ClarificationAnswerSource.LOCAL_UI,
                str(self.target),
            )
        )
        self.assertEqual(result.outcome, ClarificationOutcome.RESOLVED)
        return result.request

    def test_clarification_cannot_create_grant_or_confirmation(self) -> None:
        request = self.resolve()
        result = asyncio.run(self.service.evaluate_request(request))
        self.assertEqual(result.status, ActionStatus.DENIED)
        result = asyncio.run(self.service.evaluate_request(request, confirmed=True))
        self.assertEqual(result.status, ActionStatus.DENIED)
        self.assertEqual(self.opened, [])
        self.assertEqual(asyncio.run(self.repository.get_active_permissions()), ())

    def test_grant_then_confirmation_then_exact_execution_and_replay_rejection(
        self,
    ) -> None:
        asyncio.run(self.permissions.approve_directory(self.root, allow_open=True))
        request = self.resolve()
        result = asyncio.run(self.service.evaluate_request(request))
        self.assertEqual(result.status, ActionStatus.CONFIRMATION_REQUIRED)
        self.assertEqual(self.opened, [])
        lease = self.leases.issue_confirmation(request)
        self.assertTrue(self.leases.consume_confirmation(lease, request, approved=True))
        result = asyncio.run(self.service.evaluate_request(request, confirmed=True))
        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(self.opened, [self.target])
        self.assertFalse(
            self.leases.consume_confirmation(lease, request, approved=True)
        )

    def test_revocation_immediately_invalidates_question_and_confirmation(self) -> None:
        asyncio.run(self.permissions.approve_directory(self.root, allow_open=True))
        request = self.resolve()
        self.assertEqual(
            asyncio.run(self.service.evaluate_request(request)).status,
            ActionStatus.CONFIRMATION_REQUIRED,
        )
        lease = self.leases.issue_confirmation(request)
        self.controller.prepare(
            replace(self.request, correlation_id="revocation-pending")
        )
        pending = self.leases.pending
        asyncio.run(self.permissions.remove_approved_directory(self.root))
        self.assertIsNone(self.leases.pending)
        self.assertFalse(
            self.leases.consume_confirmation(lease, request, approved=True)
        )
        self.assertEqual(
            self.leases.resolve(
                ClarificationAnswer(
                    pending.identity,
                    ClarificationAnswerSource.LOCAL_UI,
                    str(self.target),
                )
            ).outcome,
            ClarificationOutcome.STALE,
        )
        self.assertEqual(
            asyncio.run(self.service.evaluate_request(request, confirmed=True)).status,
            ActionStatus.DENIED,
        )
        self.assertEqual(self.opened, [])

    def test_invalid_or_protected_answer_still_fails_existing_validator(self) -> None:
        request = replace(
            self.request, parameters={"path": str(self.root / "script.exe")}
        )
        (self.root / "script.exe").write_bytes(b"blocked")
        asyncio.run(self.permissions.approve_directory(self.root, allow_open=True))
        pending = self.controller.choices(self.request, (request,))
        resolved = self.controller.resolve(
            ClarificationAnswer(
                pending.identity, ClarificationAnswerSource.LOCAL_UI, choice_index=1
            )
        )
        self.assertEqual(
            asyncio.run(
                self.service.evaluate_request(resolved.request, confirmed=True)
            ).status,
            ActionStatus.DENIED,
        )
        self.assertEqual(self.opened, [])
