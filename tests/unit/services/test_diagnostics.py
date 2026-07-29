"""Tests for diagnostics snapshots."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.services.app_paths import get_app_paths
from project_akiha.services.diagnostics import (
    build_diagnostics_snapshot,
    render_diagnostics_summary,
)
from project_akiha.services.logging import LOG_BACKUP_COUNT, LOG_MAX_BYTES


class DiagnosticsTest(unittest.TestCase):
    """Verify diagnostics report local runtime paths without reading contents."""

    def test_builds_snapshot_for_runtime_paths(self) -> None:
        with TemporaryDirectory() as directory:
            paths = get_app_paths(
                environ={"LOCALAPPDATA": directory},
                project_root=Path("C:/Project Akiha"),
            )
            paths.log_dir.mkdir(parents=True)
            (paths.log_dir / "app.log").write_text("hello", encoding="utf-8")
            paths.database_path.write_bytes(b"sqlite")

            snapshot = build_diagnostics_snapshot(paths)

        self.assertTrue(snapshot.data_dir.exists)
        self.assertTrue(snapshot.log_dir.exists)
        self.assertTrue(snapshot.log_file.exists)
        self.assertEqual(snapshot.log_file.size_bytes, 5)
        self.assertTrue(snapshot.database.exists)
        self.assertEqual(snapshot.database.size_bytes, 6)
        self.assertFalse(snapshot.user_config.exists)
        self.assertEqual(snapshot.log_max_bytes, LOG_MAX_BYTES)
        self.assertEqual(snapshot.log_backup_count, LOG_BACKUP_COUNT)

    def test_renders_summary_with_statuses(self) -> None:
        with TemporaryDirectory() as directory:
            paths = get_app_paths(
                environ={"LOCALAPPDATA": directory},
                project_root=Path("C:/Project Akiha"),
            )
            paths.log_dir.mkdir(parents=True)
            (paths.log_dir / "app.log").write_text("hello", encoding="utf-8")

            summary = render_diagnostics_summary(build_diagnostics_snapshot(paths))

        self.assertIn("Project Akiha Diagnostics", summary)
        self.assertIn("Log rotation:", summary)
        self.assertIn("Log file:", summary)
        self.assertIn("(exists, 5 bytes)", summary)
        self.assertIn("User config:", summary)
        self.assertIn("(missing)", summary)


if __name__ == "__main__":
    unittest.main()
