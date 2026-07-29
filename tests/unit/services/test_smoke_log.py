"""Tests for smoke log inspection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_akiha.services.smoke_log import find_smoke_log_issues


class SmokeLogTest(unittest.TestCase):
    """Verify smoke log failure detection."""

    def test_returns_no_issues_for_clean_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "app.log"
            log_path.write_text(
                "2026-07-29 12:00:00,000 INFO [project_akiha.app] Started\n",
                encoding="utf-8",
            )

            issues = find_smoke_log_issues(log_path)

        self.assertEqual(issues, ())

    def test_finds_error_and_traceback_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "app.log"
            log_path.write_text(
                "2026-07-29 12:00:00,000 INFO [project_akiha.app] Started\n"
                "2026-07-29 12:00:01,000 ERROR [project_akiha.app] Failed\n"
                "Traceback (most recent call last):\n",
                encoding="utf-8",
            )

            issues = find_smoke_log_issues(log_path)

        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[0].line_number, 2)
        self.assertEqual(issues[1].line_number, 3)
