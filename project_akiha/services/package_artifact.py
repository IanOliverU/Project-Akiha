"""Packaged artifact validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_REQUIRED_ARTIFACT_PATHS = (
    "Akiha.exe",
    "assets",
    "assets/animations",
    "assets/animations/manifest.toml",
    "project_akiha",
    "project_akiha/config",
    "project_akiha/config/default.toml",
    "project_akiha/database",
    "project_akiha/database/migrations",
    "project_akiha/database/migrations/0013_external_integrations.sql",
    "scripts/run_gpt_sovits_api.py",
    "PySide6",
    "shiboken6",
    "av/utils.pyd",
    "faster_whisper/assets/silero_vad_v6.onnx",
)
_REQUIRED_ARTIFACT_GLOBS = ("google_genai-*.dist-info",)
_QT_MULTIMEDIA_PLUGIN_DIRS = (
    "PySide6/plugins/multimedia",
    "PySide6/qt-plugins/multimedia",
)
_QT_FFMPEG_RUNTIME_DLLS = (
    "avcodec-61.dll",
    "avformat-61.dll",
    "avutil-59.dll",
    "swresample-5.dll",
    "swscale-8.dll",
)

_FORBIDDEN_FILE_NAMES = {
    ".env",
    "credentials.json",
    "secrets.toml",
    "spotify.txt",
}
_FORBIDDEN_FILE_PREFIXES = (".env.", "client_secret")
_FORBIDDEN_DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


@dataclass(frozen=True, slots=True)
class PackageArtifactIssue:
    """One packaged artifact validation issue."""

    path: Path
    message: str


def validate_package_artifact(artifact_dir: Path) -> tuple[PackageArtifactIssue, ...]:
    """Return missing or incomplete packaged artifact items."""
    issues: list[PackageArtifactIssue] = []
    for required_path in _REQUIRED_ARTIFACT_PATHS:
        candidate = artifact_dir / required_path
        if not candidate.exists():
            issues.append(
                PackageArtifactIssue(
                    path=candidate,
                    message="Required packaged artifact path is missing.",
                )
            )

    for required_glob in _REQUIRED_ARTIFACT_GLOBS:
        if not tuple(artifact_dir.glob(required_glob)):
            issues.append(
                PackageArtifactIssue(
                    path=artifact_dir / required_glob,
                    message="Required packaged dependency metadata is missing.",
                )
            )

    multimedia_plugin_dirs = tuple(
        artifact_dir / relative_path for relative_path in _QT_MULTIMEDIA_PLUGIN_DIRS
    )
    if not any(
        (plugin_dir / "ffmpegmediaplugin.dll").is_file()
        for plugin_dir in multimedia_plugin_dirs
    ):
        issues.append(
            PackageArtifactIssue(
                path=multimedia_plugin_dirs[0],
                message=(
                    "Qt's FFmpeg multimedia backend is required for reliable "
                    "segmented speech playback."
                ),
            )
        )
    for runtime_dll in _QT_FFMPEG_RUNTIME_DLLS:
        if not any(
            (runtime_root / runtime_dll).is_file()
            for runtime_root in (artifact_dir, artifact_dir / "PySide6")
        ):
            issues.append(
                PackageArtifactIssue(
                    path=artifact_dir / runtime_dll,
                    message=(
                        "A Qt FFmpeg runtime dependency required for speech "
                        "playback is missing."
                    ),
                )
            )

    for candidate in artifact_dir.rglob("*"):
        if not candidate.is_file():
            continue
        normalized_name = candidate.name.casefold()
        is_forbidden_name = normalized_name in _FORBIDDEN_FILE_NAMES
        is_forbidden_prefix = normalized_name.startswith(_FORBIDDEN_FILE_PREFIXES)
        is_database = candidate.suffix.casefold() in _FORBIDDEN_DATABASE_SUFFIXES
        if is_forbidden_name or is_forbidden_prefix or is_database:
            issues.append(
                PackageArtifactIssue(
                    path=candidate,
                    message=(
                        "Private local data, secrets, or local database files must "
                        "not be included in a package."
                    ),
                )
            )

    migrations_dir = artifact_dir / "project_akiha/database/migrations"
    if migrations_dir.exists() and not tuple(migrations_dir.glob("*.sql")):
        issues.append(
            PackageArtifactIssue(
                path=migrations_dir,
                message="Packaged migrations directory does not contain SQL files.",
            )
        )

    return tuple(issues)
