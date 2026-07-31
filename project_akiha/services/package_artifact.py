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
    "PySide6",
    "shiboken6",
    "av/utils.pyd",
    "faster_whisper/assets/silero_vad_v6.onnx",
)

_FORBIDDEN_ARTIFACT_PATHS = ("assets/animations/akiha/Spotify.txt",)


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

    for forbidden_path in _FORBIDDEN_ARTIFACT_PATHS:
        candidate = artifact_dir / forbidden_path
        if candidate.exists():
            issues.append(
                PackageArtifactIssue(
                    path=candidate,
                    message="Private local data must not be included in a package.",
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
