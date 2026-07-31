"""Tests for Phase 8B's bounded, read-only file search executor."""

from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from project_akiha.core.actions import (
    ActionCancellationToken,
    ActionRequest,
    ActionRequestValidator,
    ActionStatus,
    FileSearchExecutor,
    ProtectedPathPolicy,
    build_default_action_registry,
)


class FileSearchExecutorTest(unittest.TestCase):
    """Verify file search remains bounded and never reads file contents."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name) / "Documents"
        self.root.mkdir()
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )

    def test_returns_case_insensitive_filename_metadata_only(self) -> None:
        report = self.root / "Quarterly-Report.txt"
        report.write_text("This content must not be read.", encoding="utf-8")

        result = asyncio.run(
            FileSearchExecutor().execute(
                self._search_action("report"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        matches = result.metadata["matches"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].name, report.name)
        self.assertEqual(matches[0].path, str(report.resolve()))
        self.assertEqual(matches[0].size_bytes, report.stat().st_size)
        self.assertNotIn("content", result.metadata)

    def test_media_only_search_does_not_spend_limit_on_other_files(self) -> None:
        for index in range(5):
            (self.root / f"FileList-{index}.txt").write_text(
                "irrelevant",
                encoding="utf-8",
            )
        song = self.root / "Megurine Luka - Elis.mp3"
        song.write_bytes(b"audio")

        result = asyncio.run(
            FileSearchExecutor(max_results=1).execute(
                self._search_action("elis", media_only=True),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(
            tuple(match.name for match in result.metadata["matches"]),
            (song.name,),
        )

    def test_enforces_recursion_depth_and_result_limit(self) -> None:
        (self.root / "report-one.txt").write_text("one", encoding="utf-8")
        first_level = self.root / "first"
        first_level.mkdir()
        (first_level / "report-two.txt").write_text("two", encoding="utf-8")
        second_level = first_level / "second"
        second_level.mkdir()
        (second_level / "report-three.txt").write_text("three", encoding="utf-8")

        result = asyncio.run(
            FileSearchExecutor(max_depth=1, max_results=2).execute(
                self._search_action("report"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertTrue(result.metadata["limited"])
        self.assertEqual(len(result.metadata["matches"]), 2)
        names = {match.name for match in result.metadata["matches"]}
        self.assertNotIn("report-three.txt", names)

    def test_honors_cancellation_before_enumerating_files(self) -> None:
        (self.root / "report.txt").write_text("report", encoding="utf-8")
        token = ActionCancellationToken()
        token.cancel()

        result = asyncio.run(
            FileSearchExecutor().execute(
                self._search_action("report"),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)

    def test_stops_when_the_registry_timeout_is_reached(self) -> None:
        (self.root / "report.txt").write_text("report", encoding="utf-8")

        with patch(
            "project_akiha.core.actions.executors.monotonic",
            side_effect=(0, 11),
        ):
            result = asyncio.run(
                FileSearchExecutor().execute(
                    self._search_action("report"),
                    cancellation_token=ActionCancellationToken(),
                )
            )

        self.assertEqual(result.status, ActionStatus.TIMED_OUT)

    def test_skips_symlinked_directories_when_supported(self) -> None:
        target = self.root.parent / "Outside"
        target.mkdir()
        (target / "report-secret.txt").write_text("secret", encoding="utf-8")
        link = self.root / "linked-outside"
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            self.skipTest("creating a directory symlink is unavailable for this user")

        result = asyncio.run(
            FileSearchExecutor().execute(
                self._search_action("report"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(result.metadata["matches"], ())
        self.assertGreaterEqual(result.metadata["skipped_entries"], 1)

    def _search_action(self, query: str, *, media_only: bool = False):
        parameters: dict[str, object] = {
            "root": str(self.root),
            "query": query,
        }
        if media_only:
            parameters["media_only"] = True
        return self.validator.validate(
            ActionRequest(
                correlation_id="search-1",
                action_id="files.search",
                source="chat",
                parameters=parameters,
            )
        )


if __name__ == "__main__":
    unittest.main()
