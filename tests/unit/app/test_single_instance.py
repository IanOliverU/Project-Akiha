"""Tests for user-scoped single-instance ownership."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest.mock import MagicMock, patch
from uuid import uuid4

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from project_akiha.app import single_instance
from project_akiha.app.single_instance import (
    SingleInstanceCoordinator,
    SingleInstanceRole,
    build_single_instance_name,
)


class SingleInstanceCoordinatorTest(unittest.TestCase):
    """Verify primary ownership, activation handoff, and cleanup."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_server_name_is_stable_and_does_not_expose_the_data_path(self) -> None:
        with TemporaryDirectory() as directory:
            data_dir = Path(directory) / "Private User" / "Akiha"
            first = build_single_instance_name(data_dir)
            second = build_single_instance_name(data_dir)
            other = build_single_instance_name(data_dir / "Other")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotIn("Private User", first)
        self.assertTrue(first.startswith("project-akiha-"))

    def test_secondary_notifies_primary_and_does_not_claim_ownership(self) -> None:
        name = f"project-akiha-test-{uuid4().hex}"
        primary = SingleInstanceCoordinator(name)
        activations: list[bool] = []
        secondary_roles: list[SingleInstanceRole] = []
        loop = QEventLoop()

        def record_activation() -> None:
            activations.append(True)
            loop.quit()

        primary.activation_requested.connect(record_activation)

        def start_secondary() -> None:
            secondary = SingleInstanceCoordinator(name)
            secondary_roles.append(secondary.start())
            secondary.close()

        try:
            self.assertEqual(primary.start(), SingleInstanceRole.PRIMARY)
            thread = Thread(target=start_secondary)
            thread.start()
            QTimer.singleShot(2_000, loop.quit)
            loop.exec()
            thread.join(timeout=1)

            self.assertEqual(secondary_roles, [SingleInstanceRole.SECONDARY])
            self.assertEqual(activations, [True])
            self.assertTrue(primary.is_primary)
        finally:
            primary.close()
            self.app.processEvents()

    def test_simultaneous_start_loser_retries_the_primary(self) -> None:
        coordinator = SingleInstanceCoordinator(f"project-akiha-test-{uuid4().hex}")
        server = MagicMock()
        server.listen.return_value = False
        with (
            patch.object(
                coordinator,
                "_notify_existing_instance",
                side_effect=[
                    single_instance._ProbeResult.STALE_OR_MISSING,
                    single_instance._ProbeResult.NOTIFIED,
                ],
            ),
            patch.object(single_instance, "QLocalServer") as server_type,
        ):
            server_type.return_value = server

            role = coordinator.start()

        self.assertEqual(role, SingleInstanceRole.SECONDARY)
        server.listen.assert_called_once()
        server.deleteLater.assert_called_once()

    def test_graceful_close_releases_ownership_for_the_next_launch(self) -> None:
        name = f"project-akiha-test-{uuid4().hex}"
        first = SingleInstanceCoordinator(name)
        replacement = SingleInstanceCoordinator(name)
        try:
            self.assertEqual(first.start(), SingleInstanceRole.PRIMARY)
            first.close()
            self.app.processEvents()

            self.assertEqual(replacement.start(), SingleInstanceRole.PRIMARY)
            self.assertTrue(replacement.is_primary)
        finally:
            replacement.close()
            first.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
