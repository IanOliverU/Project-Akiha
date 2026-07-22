"""Tests for runtime path resolution."""

from __future__ import annotations

import unittest
from pathlib import Path

from project_akiha.services.app_paths import get_app_paths


class AppPathsTest(unittest.TestCase):
    """Verify app data path selection."""

    def test_uses_local_app_data_when_available(self) -> None:
        project_root = Path("C:/Project Akiha")
        paths = get_app_paths(
            environ={"LOCALAPPDATA": "C:/Users/Test/Local"},
            project_root=project_root,
        )

        self.assertEqual(paths.data_dir, Path("C:/Users/Test/Local") / "Akiha")
        self.assertEqual(paths.log_dir, paths.data_dir / "logs")
        self.assertEqual(paths.state_dir, paths.data_dir / "state")
        self.assertEqual(paths.user_config_path, paths.data_dir / "user_config.toml")
        self.assertEqual(paths.asset_dir, project_root / "assets")

    def test_falls_back_to_app_data(self) -> None:
        paths = get_app_paths(
            environ={"APPDATA": "C:/Users/Test/Roaming"},
            project_root=Path("C:/Project Akiha"),
        )

        self.assertEqual(paths.data_dir, Path("C:/Users/Test/Roaming") / "Akiha")


if __name__ == "__main__":
    unittest.main()
