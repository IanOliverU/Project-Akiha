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

    def test_reports_missing_google_genai_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            (artifact_dir / "google_genai-2.17.0.dist-info").rmdir()

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 1)
        self.assertIn("metadata", issues[0].message)

    def test_reports_missing_qt_multimedia_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            plugin = artifact_dir / "PySide6/plugins/multimedia/ffmpegmediaplugin.dll"
            plugin.unlink()

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 1)
        self.assertIn("FFmpeg multimedia backend", issues[0].message)

    def test_reports_missing_qt_ffmpeg_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            (artifact_dir / "PySide6/avcodec-61.dll").unlink()

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 1)
        self.assertIn("FFmpeg runtime dependency", issues[0].message)

    def test_rejects_personal_spotify_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            private_export = artifact_dir / "assets/animations/akiha/Spotify.txt"
            private_export.parent.mkdir(parents=True)
            private_export.write_text("private listening history", encoding="utf-8")

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 1)
        self.assertIn("Private local data", issues[0].message)

    def test_rejects_secret_and_local_database_files_anywhere(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            artifact_dir = Path(directory)
            _write_complete_artifact(artifact_dir)
            private_dir = artifact_dir / "private"
            private_dir.mkdir()
            (private_dir / ".env.production").write_text(
                "API_KEY=private",
                encoding="utf-8",
            )
            (private_dir / "client_secret.json").write_text(
                "{}",
                encoding="utf-8",
            )
            (private_dir / "akiha.sqlite3").write_bytes(b"")

            issues = validate_package_artifact(artifact_dir)

        self.assertEqual(len(issues), 3)
        self.assertTrue(
            all("must not be included" in issue.message for issue in issues)
        )


def _write_complete_artifact(artifact_dir: Path) -> None:
    (artifact_dir / "assets/animations").mkdir(parents=True)
    (artifact_dir / "project_akiha/config").mkdir(parents=True)
    (artifact_dir / "project_akiha/database/migrations").mkdir(parents=True)
    (artifact_dir / "scripts").mkdir()
    (artifact_dir / "PySide6/plugins/multimedia").mkdir(parents=True)
    (artifact_dir / "shiboken6").mkdir()
    (artifact_dir / "av").mkdir()
    (artifact_dir / "faster_whisper/assets").mkdir(parents=True)
    (artifact_dir / "google_genai-2.17.0.dist-info").mkdir()
    (artifact_dir / "Akiha.exe").write_bytes(b"")
    (artifact_dir / "PySide6/plugins/multimedia/ffmpegmediaplugin.dll").write_bytes(b"")
    for runtime_dll in (
        "avcodec-61.dll",
        "avformat-61.dll",
        "avutil-59.dll",
        "swresample-5.dll",
        "swscale-8.dll",
    ):
        (artifact_dir / "PySide6" / runtime_dll).write_bytes(b"")
    (artifact_dir / "av/utils.pyd").write_bytes(b"")
    (artifact_dir / "faster_whisper/assets/silero_vad_v6.onnx").write_bytes(b"")
    (artifact_dir / "scripts/run_gpt_sovits_api.py").write_text(
        "",
        encoding="utf-8",
    )
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
