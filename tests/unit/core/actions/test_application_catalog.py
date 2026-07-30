"""Tests for trusted application discovery and argument-free launching."""

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
    AllowlistedApplicationExecutor,
    ApplicationCatalog,
    ProtectedPathPolicy,
    build_default_action_registry,
)


class ApplicationCatalogTest(unittest.TestCase):
    """Verify discovery stays inside the fixed application catalog."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.program_files = self.root / "Program Files"
        self.local_app_data = self.root / "LocalAppData"
        self.app_data = self.root / "AppData"
        self.environ = {
            "ProgramW6432": str(self.program_files),
            "ProgramFiles": str(self.program_files),
            "LOCALAPPDATA": str(self.local_app_data),
            "APPDATA": str(self.app_data),
        }

    def test_discovers_known_installation_locations(self) -> None:
        expected = {
            "chrome": self.program_files
            / "Google"
            / "Chrome"
            / "Application"
            / "chrome.exe",
            "discord": self.local_app_data / "Discord" / "app-1.0" / "Discord.exe",
            "spotify": self.app_data / "Spotify" / "Spotify.exe",
            "vscode": self.local_app_data
            / "Programs"
            / "Microsoft VS Code"
            / "Code.exe",
        }
        for path in expected.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stub", encoding="utf-8")

        catalog = ApplicationCatalog(self.environ)
        discovered = {item.application_id: item for item in catalog.discover()}

        self.assertEqual(set(discovered), {"chrome", "discord", "spotify", "vscode"})
        for application_id, path in expected.items():
            self.assertEqual(discovered[application_id].executable, path.resolve())
            self.assertTrue(discovered[application_id].is_available)

    def test_reports_missing_known_apps_without_guessing_paths(self) -> None:
        catalog = ApplicationCatalog(self.environ)

        result = catalog.resolve("spotify")

        self.assertFalse(result.is_available)
        self.assertIsNone(result.executable)

    def test_rejects_unknown_catalog_id(self) -> None:
        with self.assertRaises(ValueError):
            ApplicationCatalog(self.environ).resolve("powershell")


class AllowlistedApplicationExecutorTest(unittest.TestCase):
    """Verify only the catalog-resolved executable reaches the launcher."""

    def setUp(self) -> None:
        self._temporary_directory = TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.executable = self.root / "chrome.exe"
        self.executable.write_text("stub", encoding="utf-8")
        self.catalog = _SingleApplicationCatalog(self.executable)
        self.validator = ActionRequestValidator(
            build_default_action_registry(),
            ProtectedPathPolicy(),
        )
        self.launched: list[Path] = []

    def test_launches_resolved_application_without_ai_path_or_arguments(self) -> None:
        result = asyncio.run(
            AllowlistedApplicationExecutor(
                self.catalog,
                self._launch,
            ).execute(
                self._action("chrome"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.SUCCESS)
        self.assertEqual(self.launched, [self.executable.resolve()])
        self.assertEqual(result.metadata["application_id"], "chrome")

    def test_missing_application_is_reported_without_launching(self) -> None:
        result = asyncio.run(
            AllowlistedApplicationExecutor(
                _SingleApplicationCatalog(None),
                self._launch,
            ).execute(
                self._action("chrome"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.TARGET_UNAVAILABLE,
        )
        self.assertEqual(self.launched, [])

    def test_cancellation_does_not_launch(self) -> None:
        token = ActionCancellationToken()
        token.cancel()

        result = asyncio.run(
            AllowlistedApplicationExecutor(self.catalog, self._launch).execute(
                self._action("chrome"),
                cancellation_token=token,
            )
        )

        self.assertEqual(result.status, ActionStatus.CANCELLED)
        self.assertEqual(self.launched, [])

    def test_launcher_failure_is_sanitized(self) -> None:
        def fail(_: Path) -> None:
            raise OSError("private process details")

        result = asyncio.run(
            AllowlistedApplicationExecutor(self.catalog, fail).execute(
                self._action("chrome"),
                cancellation_token=ActionCancellationToken(),
            )
        )

        self.assertEqual(result.status, ActionStatus.FAILED)
        self.assertEqual(
            result.failure_category,
            ActionFailureCategory.EXECUTION_FAILED,
        )
        self.assertNotIn("private process details", result.summary)

    def _action(self, application_id: str):
        return self.validator.validate(
            ActionRequest(
                correlation_id="launch-1",
                action_id="applications.launch",
                source="chat",
                parameters={"application_id": application_id},
            )
        )

    def _launch(self, path: Path) -> None:
        self.launched.append(path.resolve())


class _SingleApplicationCatalog:
    def __init__(self, executable: Path | None) -> None:
        self.executable = executable

    def resolve(self, application_id: str):
        from project_akiha.core.actions.application_catalog import InstalledApplication

        return InstalledApplication(application_id, "Google Chrome", self.executable)


if __name__ == "__main__":
    unittest.main()
