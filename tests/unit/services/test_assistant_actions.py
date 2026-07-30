"""Tests for fail-closed Phase 8A action orchestration."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionFailureCategory,
    ActionPermissionPolicy,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    FileSearchExecutor,
    OpenDirectoryExecutor,
    OpenFileExecutor,
    PermissionDecision,
    ProtectedPathPolicy,
    build_default_action_registry,
)
from project_akiha.database import SQLiteActionRepository
from project_akiha.services.assistant_actions import AssistantActionService
from project_akiha.services.assistant_permissions import AssistantPermissionService


class AssistantActionServiceTest(unittest.TestCase):
    """Verify Phase 8A evaluates and audits without desktop execution."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.approved_root = self.root / "Documents"
        self.approved_root.mkdir()
        self.outside_root = self.root / "Outside"
        self.outside_root.mkdir()
        self.path_policy = ProtectedPathPolicy()
        registry = build_default_action_registry()
        self.repository = SQLiteActionRepository(self.root / "akiha.sqlite3")
        self.permissions = AssistantPermissionService(
            self.repository,
            self.path_policy,
        )
        self.service = AssistantActionService(
            ActionRequestValidator(registry, self.path_policy),
            ActionPermissionPolicy(self.path_policy),
            self.repository,
            self.repository,
            executors=(
                FileSearchExecutor(max_depth=2, max_results=10),
                OpenDirectoryExecutor(self._open_directory),
                OpenFileExecutor(self._open_file),
            ),
        )
        self.opened_directories: list[Path] = []
        self.opened_files: list[Path] = []

    def test_plain_provider_text_has_no_action_entry_point(self) -> None:
        with self.assertRaises(TypeError):
            asyncio.run(
                self.service.evaluate_request(  # type: ignore[arg-type]
                    "Please open Discord."
                )
            )

        audits = asyncio.run(self.repository.get_recent_action_audits(limit=10))
        self.assertEqual(audits, ())

    def test_unknown_action_is_denied_and_audited(self) -> None:
        result = asyncio.run(
            self.service.evaluate_request(
                self._request("system.run", {"command": "whoami"})
            )
        )
        audits = asyncio.run(self.repository.get_recent_action_audits(limit=10))

        self.assertEqual(result.status, ActionStatus.DENIED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.UNKNOWN_ACTION,
        )
        self.assertEqual(audits[0].failure_category, result.failure_category)
        self.assertIsNone(audits[0].normalized_target)

    def test_valid_request_without_permission_is_denied(self) -> None:
        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.search",
                    {"root": str(self.approved_root), "query": "report"},
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.DENIED)
        self.assertEqual(result.permission_decision, PermissionDecision.MISSING)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.PERMISSION_REQUIRED,
        )

    def test_granted_action_stops_at_unavailable_executor(self) -> None:
        asyncio.run(self.permissions.grant_application("spotify"))

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "applications.launch",
                    {"application_id": "spotify"},
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.UNAVAILABLE)
        self.assertEqual(result.permission_decision, PermissionDecision.GRANTED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.EXECUTOR_UNAVAILABLE,
        )

    def test_open_file_requires_confirmation_before_executor(self) -> None:
        file_path = self.approved_root / "notes.txt"
        file_path.write_text("notes", encoding="utf-8")
        asyncio.run(self.permissions.grant_directory("files.open", self.approved_root))
        request = self._request("files.open", {"path": str(file_path)})

        pending = asyncio.run(self.service.evaluate_request(request))
        confirmed = asyncio.run(self.service.evaluate_request(request, confirmed=True))

        self.assertEqual(pending.status, ActionStatus.CONFIRMATION_REQUIRED)
        self.assertEqual(confirmed.status, ActionStatus.SUCCESS)
        self.assertEqual(self.opened_files, [file_path.resolve()])

    def test_traversal_escape_is_not_covered_by_directory_grant(self) -> None:
        asyncio.run(
            self.permissions.grant_directory("files.search", self.approved_root)
        )

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.search",
                    {
                        "root": str(self.approved_root / ".." / "Outside"),
                        "query": "secret",
                    },
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.DENIED)
        self.assertEqual(result.permission_decision, PermissionDecision.MISSING)

    def test_approved_directory_search_executes_and_is_audited(self) -> None:
        report = self.approved_root / "report.txt"
        report.write_text("private contents", encoding="utf-8")
        asyncio.run(
            self.permissions.approve_directory(
                self.approved_root,
                allow_search=True,
                allow_open=False,
            )
        )

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.search",
                    {"root": str(self.approved_root), "query": "report"},
                )
            )
        )
        audits = asyncio.run(self.repository.get_recent_action_audits(limit=1))

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["matches"][0].path, str(report.resolve()))
        self.assertEqual(result.permission_decision, PermissionDecision.GRANTED)
        self.assertEqual(audits[0].result_status, ActionStatus.SUCCESS)
        self.assertEqual(
            audits[0].normalized_target,
            str(self.approved_root.resolve()),
        )

    def test_search_cancellation_is_recorded_without_results(self) -> None:
        (self.approved_root / "report.txt").write_text("report", encoding="utf-8")
        asyncio.run(
            self.permissions.grant_directory("files.search", self.approved_root)
        )
        token = ActionCancellationToken()
        token.cancel()

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.search",
                    {"root": str(self.approved_root), "query": "report"},
                ),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertNotIn("matches", result.metadata)

    def test_approved_directory_open_uses_injected_desktop_opener(self) -> None:
        asyncio.run(
            self.permissions.approve_directory(
                self.approved_root,
                allow_search=False,
                allow_open=True,
            )
        )

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.open_directory",
                    {"path": str(self.approved_root)},
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(self.opened_directories, [self.approved_root.resolve()])
        self.assertEqual(
            result.metadata["opened_directory"],
            str(self.approved_root.resolve()),
        )

    def test_directory_open_does_not_call_opener_without_permission(self) -> None:
        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.open_directory",
                    {"path": str(self.approved_root)},
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.DENIED)
        self.assertEqual(self.opened_directories, [])

    def test_directory_open_cancellation_does_not_call_opener(self) -> None:
        asyncio.run(self.permissions.grant_directory("files.open", self.approved_root))
        token = ActionCancellationToken()
        token.cancel()

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.open_directory",
                    {"path": str(self.approved_root)},
                ),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(self.opened_directories, [])

    def test_deleted_approved_root_fails_without_broadening_access(self) -> None:
        asyncio.run(
            self.permissions.grant_directory("files.search", self.approved_root)
        )
        self.approved_root.rmdir()

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "files.search",
                    {"root": str(self.approved_root), "query": "report"},
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.TARGET_UNAVAILABLE,
        )

    def test_ai_supplied_executable_path_is_denied_before_permission(self) -> None:
        asyncio.run(self.permissions.grant_application("chrome"))

        result = asyncio.run(
            self.service.evaluate_request(
                self._request(
                    "applications.launch",
                    {
                        "application_id": "chrome",
                        "path": r"C:\Windows\System32\cmd.exe",
                    },
                )
            )
        )

        self.assertEqual(result.status, ActionStatus.DENIED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.INVALID_PARAMETERS,
        )
        self.assertEqual(
            result.permission_decision,
            PermissionDecision.NOT_EVALUATED,
        )

    def _open_directory(self, path: Path) -> None:
        self.opened_directories.append(path.resolve())

    def _open_file(self, path: Path) -> None:
        self.opened_files.append(path.resolve())

    @staticmethod
    def _request(
        action_id: str,
        parameters: dict[str, object],
    ) -> ActionRequest:
        return ActionRequest(
            correlation_id="request-1",
            action_id=action_id,
            source="chat",
            parameters=parameters,
        )


if __name__ == "__main__":
    unittest.main()
