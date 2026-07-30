"""Tests for protected-path and scope containment policy."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from project_akiha.core.actions import (
    ActionFailureCategory,
    ActionValidationError,
    ProtectedPathPolicy,
)


class ProtectedPathPolicyTest(unittest.TestCase):
    """Verify unsafe or ambiguous Windows paths fail closed."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.safe_root = self.root / "Documents"
        self.safe_root.mkdir()
        self.protected_root = self.root / "Windows"
        self.protected_root.mkdir()
        self.credential_path = self.root / "Akiha" / "state" / "credentials.json"
        self.credential_path.parent.mkdir(parents=True)
        self.credential_path.write_text("encrypted", encoding="utf-8")
        self.policy = ProtectedPathPolicy(
            protected_roots=(self.protected_root,),
            credential_path=self.credential_path,
        )

    def test_canonicalizes_safe_absolute_path(self) -> None:
        child = self.safe_root / "Projects"
        child.mkdir()

        result = self.policy.validate_path(str(self.safe_root / "." / "Projects"))

        self.assertEqual(result, child.resolve())

    def test_rejects_relative_path(self) -> None:
        self._assert_invalid_target("Documents")

    def test_rejects_protected_root_and_descendant(self) -> None:
        self._assert_invalid_target(str(self.protected_root))
        self._assert_invalid_target(str(self.protected_root / "System32"))

    def test_rejects_encrypted_credential_path(self) -> None:
        self._assert_invalid_target(str(self.credential_path))

    def test_rejects_network_device_and_alternate_stream_paths(self) -> None:
        self._assert_invalid_target(r"\\server\share")
        self._assert_invalid_target(r"\\?\C:\Users")
        self._assert_invalid_target(f"{self.safe_root}:secret")

    def test_rejects_drive_root(self) -> None:
        self._assert_invalid_target(str(Path(self.root.anchor)))

    def test_scope_check_accepts_descendant_and_rejects_escape(self) -> None:
        child = self.safe_root / "Projects"
        child.mkdir()
        outside = self.root / "Outside"
        outside.mkdir()

        self.assertTrue(self.policy.is_within(child, self.safe_root))
        self.assertFalse(self.policy.is_within(outside, self.safe_root))
        self.assertFalse(
            self.policy.is_within(self.safe_root / ".." / "Outside", self.safe_root)
        )

    def test_rejects_existing_link_or_reparse_component_when_supported(self) -> None:
        outside = self.root / "Outside"
        outside.mkdir()
        link = self.safe_root / "linked"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"directory symlinks are unavailable: {error}")

        self._assert_invalid_target(str(link / "file.txt"))

    def test_rejects_path_when_reparse_detector_flags_it(self) -> None:
        with patch(
            "project_akiha.core.actions.path_policy."
            "_contains_existing_reparse_point",
            return_value=True,
        ):
            self._assert_invalid_target(str(self.safe_root))

    def _assert_invalid_target(self, value: str) -> None:
        with self.assertRaises(ActionValidationError) as captured:
            self.policy.validate_path(value)
        self.assertEqual(
            captured.exception.category,
            ActionFailureCategory.INVALID_TARGET,
        )


if __name__ == "__main__":
    unittest.main()
