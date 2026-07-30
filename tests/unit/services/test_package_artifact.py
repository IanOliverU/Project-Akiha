"""Tests for packaged artifact validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from project_akiha.services.package_artifact import validate_package_artifact


class PackageArtifactTest(unittest.TestCase):
    """Verify standalone artifact validation."""

    def test_accepts_complete_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(issues, ())

    def test_reports_missing_required_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            (artifact_dir / "assets/animations/manifest.toml").unlink()

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 1)
        self.assertIn("manifest.toml", str(issues[0].path))

    def test_reports_empty_migrations_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            for migration in (artifact_dir / "project_akiha/database/migrations").glob(
                "*.sql"
            ):
                migration.unlink()

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 1)
        self.assertIn("SQL files", issues[0].message)


def _write_complete_artifact(artifact_dir: Path) -> None:
    (artifact_dir / "assets/animations").mkdir(parents=True)
    (artifact_dir / "project_akiha/config").mkdir(parents=True)
    (artifact_dir / "project_akiha/database/migrations").mkdir(parents=True)
    (artifact_dir / "PySide6").mkdir()
    (artifact_dir / "shiboken6").mkdir()
    (artifact_dir / "av").mkdir()
    (artifact_dir / "faster_whisper/assets").mkdir(parents=True)
    (artifact_dir / "Akiha.exe").write_bytes(b"")
    (artifact_dir / "av/utils.pyd").write_bytes(b"")
    (artifact_dir / "faster_whisper/assets/silero_vad_v6.onnx").write_bytes(b"")
    (artifact_dir / "assets/animations/manifest.toml").write_text(
        "",
        encoding="utf-8",
    )
    (artifact_dir / "project_akiha/config/default.toml").write_text(
        "",
        encoding="utf-8",
    )
    (artifact_dir / "project_akiha/database/migrations/0001_test.sql").write_text(
        "",
        encoding="utf-8",
    )
