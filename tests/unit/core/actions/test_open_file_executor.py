"""Tests for the confirmation-gated passive-file executor."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionFailureCategory,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    OpenFileExecutor,
    ProtectedPathPolicy,
    build_default_action_registry,
)


class OpenFileExecutorTest(unittest.TestCase):
    """Verify only validated passive files reach the desktop opener."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "Documents"
        self.root.mkdir()
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )
        self.opened_files: list[Path] = []
        self.executor = OpenFileExecutor(self._open_file)

    def test_opens_allowlisted_file_after_service_confirmation_checkpoint(self) -> None:
        file_path = self.root / "notes.txt"
        file_path.write_text("notes", encoding="utf-8")

        result = asyncio.run(
            self.executor.execute(
                self._open_action(file_path),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(self.opened_files, [file_path.resolve()])
        self.assertEqual(result.metadata["opened_file"], str(file_path.resolve()))

    def test_cancellation_does_not_call_desktop_opener(self) -> None:
        file_path = self.root / "notes.txt"
        file_path.write_text("notes", encoding="utf-8")
        token = ActionCancellationToken()
        token.cancel()

        result = asyncio.run(
            self.executor.execute(
                self._open_action(file_path),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(self.opened_files, [])

    def test_rechecks_file_if_it_disappears_after_validation(self) -> None:
        file_path = self.root / "notes.txt"
        file_path.write_text("notes", encoding="utf-8")
        action = self._open_action(file_path)
        file_path.unlink()

        result = asyncio.run(
            self.executor.execute(
                action,
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.TARGET_UNAVAILABLE,
        )
        self.assertEqual(self.opened_files, [])

    def test_opener_failure_is_sanitized(self) -> None:
        file_path = self.root / "notes.txt"
        file_path.write_text("notes", encoding="utf-8")

        def fail(_: Path) -> None:
            raise OSError("private desktop error")

        result = asyncio.run(
            OpenFileExecutor(fail).execute(
                self._open_action(file_path),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.EXECUTION_FAILED,
        )
        self.assertNotIn("private desktop error", result.summary)

    def _open_action(self, file_path: Path):
        return self.validator.validate(
            ActionRequest(
                correlation_id="open-file-1",
                action_id="files.open",
                source="chat",
                parameters={"path": str(file_path)},
            )
        )

    def _open_file(self, path: Path) -> None:
        self.opened_files.append(path.resolve())


if __name__ == "__main__":
    unittest.main()
