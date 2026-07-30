"""Tests for typed assistant permission management."""

from __future__ import annotations

import asyncio
import shutil
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

    def test_approves_lists_and_updates_directory_capabilities(self) -> None:
        approved = asyncio.run(self.service.approve_directory(self.safe_root))
        listed = asyncio.run(self.service.get_approved_directories())

        self.assertTrue(approved.can_search)
        self.assertFalse(approved.can_open)
        self.assertTrue(approved.is_available)
        self.assertEqual(listed, (approved,))

        updated = asyncio.run(
            self.service.approve_directory(
                self.safe_root,
                allow_search=False,
                allow_open=True,
            )
        )
        listed_after_update = asyncio.run(self.service.get_approved_directories())

        self.assertFalse(updated.can_search)
        self.assertTrue(updated.can_open)
        self.assertEqual(listed_after_update, (updated,))

    def test_approved_directory_listing_excludes_application_grants(self) -> None:
        asyncio.run(self.service.grant_application("spotify"))

        self.assertEqual(
            asyncio.run(self.service.get_approved_directories()),
            (),
        )

    def test_lists_missing_directory_as_unavailable_and_still_removes_it(self) -> None:
        approved = asyncio.run(self.service.approve_directory(self.safe_root))
        shutil.rmtree(self.safe_root)

        listed = asyncio.run(self.service.get_approved_directories())
        removed = asyncio.run(self.service.remove_approved_directory(approved.root))

        self.assertEqual(len(listed), 1)
        self.assertFalse(listed[0].is_available)
        self.assertTrue(removed)
        self.assertEqual(
            asyncio.run(self.service.get_approved_directories()),
            (),
        )

    def test_remove_unknown_directory_is_idempotent(self) -> None:
        self.assertFalse(
            asyncio.run(self.service.remove_approved_directory(self.root / "Unknown"))
        )

    def test_rejects_directory_without_any_capability(self) -> None:
        with self.assertRaises(ValueError):
            asyncio.run(
                self.service.approve_directory(
                    self.safe_root,
                    allow_search=False,
                    allow_open=False,
                )
            )


if __name__ == "__main__":
    unittest.main()
