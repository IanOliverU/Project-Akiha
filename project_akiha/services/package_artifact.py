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
    "scripts/run_gpt_sovits_api.py",
    "PySide6",
    "shiboken6",
    "av/utils.pyd",
    "faster_whisper/assets/silero_vad_v6.onnx",
)
_REQUIRED_ARTIFACT_GLOBS = ("google_genai-*.dist-info",)

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
