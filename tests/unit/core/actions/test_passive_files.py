"""Tests for the passive file-extension boundary."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionValidationError,
    PassiveFilePolicy,
)


class PassiveFilePolicyTest(unittest.TestCase):
    """Verify passive opening stays default-deny and regular-file-only."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.policy = PassiveFilePolicy()

    def test_accepts_allowlisted_extensions_case_insensitively(self) -> None:
        for name in (
            "note.TXT",
            "readme.md",
            "image.png",
            "audio.MP3",
            "clip.webm",
            "guide.PDF",
        ):
            path = self.root / name
            path.write_text("sample", encoding="utf-8")
            self.assertTrue(self.policy.is_allowed(path), name)

    def test_rejects_active_and_unknown_extensions(self) -> None:
        for name in (
            "installer.exe",
            "script.ps1",
            "shortcut.lnk",
            "site.url",
            "report.docx",
            "budget.xlsm",
        ):
            path = self.root / name
            path.write_text("sample", encoding="utf-8")
            with self.assertRaises(ActionValidationError) as captured:
                self.policy.validate_file(path)
            self.assertEqual(
                captured.exception.category, ActionFailureCategory.INVALID_TARGET
            )

    def test_rejects_directory_even_when_suffix_is_allowlisted(self) -> None:
        directory = self.root / "folder.txt"
        directory.mkdir()
        with self.assertRaises(ActionValidationError) as captured:
            self.policy.validate_file(directory)
        self.assertEqual(
            captured.exception.category, ActionFailureCategory.INVALID_TARGET
        )

    def test_reports_missing_file_as_unavailable(self) -> None:
        with self.assertRaises(ActionValidationError) as captured:
            self.policy.validate_file(self.root / "missing.txt")
        self.assertEqual(
            captured.exception.category, ActionFailureCategory.TARGET_UNAVAILABLE
        )

    def test_supports_a_custom_case_insensitive_allowlist(self) -> None:
        path = self.root / "sample.CUSTOM"
        path.write_text("sample", encoding="utf-8")
        policy = PassiveFilePolicy({".custom"})
        self.assertEqual(policy.allowed_extensions, frozenset({".custom"}))
        self.assertTrue(policy.is_allowed(path))


if __name__ == "__main__":
    unittest.main()
