"""Tests for typed assistant permission management."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.core.actions import ProtectedPathPolicy
from project_akiha.database import SQLiteActionRepository
from project_akiha.services.assistant_permissions import AssistantPermissionService


class AssistantPermissionServiceTest(unittest.TestCase):
    """Verify generic or protected permissions cannot be created."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.safe_root = self.root / "Documents"
        self.safe_root.mkdir()
        self.protected_root = self.root / "Windows"
        self.protected_root.mkdir()
        repository = SQLiteActionRepository(self.root / "akiha.sqlite3")
        self.service = AssistantPermissionService(
            repository,
            ProtectedPathPolicy(protected_roots=(self.protected_root,)),
        )

    def test_grants_only_known_file_capability_for_safe_root(self) -> None:
        grant = asyncio.run(
            self.service.grant_directory("files.search", self.safe_root)
        )

        self.assertEqual(grant.capability, "files.search")
        self.assertEqual(grant.target, str(self.safe_root.resolve()))

        with self.assertRaises(ValueError):
            asyncio.run(self.service.grant_directory("filesystem.all", self.safe_root))

    def test_rejects_protected_directory_grant(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(
                self.service.grant_directory("files.search", self.protected_root)
            )

    def test_rejects_nonexistent_directory_grant(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(
                self.service.grant_directory(
                    "files.search",
                    self.root / "Missing",
                )
            )

    def test_grants_only_allowlisted_application_identifier(self) -> None:
        grant = asyncio.run(self.service.grant_application(" Spotify "))

        self.assertEqual(grant.capability, "applications.launch")
        self.assertEqual(grant.target, "spotify")

        with self.assertRaises(ValueError):
            asyncio.run(self.service.grant_application("powershell"))


if __name__ == "__main__":
    unittest.main()
