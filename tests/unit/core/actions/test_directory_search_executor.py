"""Tests for bounded descendant-directory discovery."""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    DirectorySearchExecutor,
    ProtectedPathPolicy,
    build_default_action_registry,
)


class DirectorySearchExecutorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "Downloads"
        self.root.mkdir()
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_finds_descendant_directories_and_ignores_files(self) -> None:
        compressed = self.root / "Compressed"
        compressed.mkdir()
        (self.root / "Compressed.zip").write_bytes(b"archive")

        result = asyncio.run(
            DirectorySearchExecutor().execute(
                self._action("compress"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(
            tuple(match.path for match in result.metadata["matches"]),
            (str(compressed),),
        )

    def test_match_all_remains_bounded(self) -> None:
        for name in ("Alpha", "Beta", "Gamma"):
            (self.root / name).mkdir()

        result = asyncio.run(
            DirectorySearchExecutor(max_results=2).execute(
                self._action("missing", match_all=True),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(len(result.metadata["matches"]), 2)
        self.assertTrue(result.metadata["limited"])

    def test_skips_linked_directory_when_supported(self) -> None:
        outside = self.root.parent / "Outside"
        outside.mkdir()
        (outside / "Compressed").mkdir()
        link = self.root / "Linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError:
            self.skipTest("creating a directory symlink is unavailable for this user")

        result = asyncio.run(
            DirectorySearchExecutor().execute(
                self._action("compressed"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.metadata["matches"], ())
        self.assertGreaterEqual(result.metadata["skipped_entries"], 1)

    def test_honors_cancellation(self) -> None:
        token = ActionCancellationToken()
        token.cancel()

        result = asyncio.run(
            DirectorySearchExecutor().execute(
                self._action("compressed"),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertIn("Directory search", result.summary)

    def _action(self, query: str, *, match_all: bool = False):
        return self.validator.validate(
            ActionRequest(
                correlation_id="directory-search-1",
                action_id="directories.search",
                source="chat",
                parameters={
                    "root": str(self.root),
                    "query": query,
                    "match_all": match_all,
                },
            )
        )


if __name__ == "__main__":
    unittest.main()
