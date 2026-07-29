"""Diagnostics helpers for support and release smoke checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from project_akiha.services.app_paths import AppPaths
from project_akiha.services.logging import LOG_BACKUP_COUNT, LOG_MAX_BYTES


@dataclass(frozen=True, slots=True)
class DiagnosticPath:
    """A local runtime path that may be useful during support."""

    label: str
    path: Path
    exists: bool
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticsSnapshot:
    """A compact view of important local diagnostics information."""

    data_dir: DiagnosticPath
    log_dir: DiagnosticPath
    log_file: DiagnosticPath
    database: DiagnosticPath
    user_config: DiagnosticPath
    credentials: DiagnosticPath
    state_dir: DiagnosticPath
    log_max_bytes: int
    log_backup_count: int

    @property
    def paths(self) -> tuple[DiagnosticPath, ...]:
        """Return all tracked paths in display order."""
        return (
            self.data_dir,
            self.log_dir,
            self.log_file,
            self.database,
            self.user_config,
            self.credentials,
            self.state_dir,
        )


def build_diagnostics_snapshot(paths: AppPaths) -> DiagnosticsSnapshot:
    """Build a diagnostics snapshot without reading private data contents."""
    log_file = paths.log_dir / "app.log"
    return DiagnosticsSnapshot(
        data_dir=_describe_path("Data directory", paths.data_dir),
        log_dir=_describe_path("Log directory", paths.log_dir),
        log_file=_describe_path("Log file", log_file),
        database=_describe_path("SQLite database", paths.database_path),
        user_config=_describe_path("User config", paths.user_config_path),
        credentials=_describe_path(
            "Encrypted credentials",
            paths.credential_path,
        ),
        state_dir=_describe_path("State directory", paths.state_dir),
        log_max_bytes=LOG_MAX_BYTES,
        log_backup_count=LOG_BACKUP_COUNT,
    )


def render_diagnostics_summary(snapshot: DiagnosticsSnapshot) -> str:
    """Render a human-readable diagnostics summary."""
    lines = [
        "Project Akiha Diagnostics",
        f"Log rotation: {snapshot.log_max_bytes} bytes, "
        f"{snapshot.log_backup_count} backups",
        "",
        "Paths:",
    ]
    for item in snapshot.paths:
        status = "exists" if item.exists else "missing"
        size = f", {item.size_bytes} bytes" if item.size_bytes is not None else ""
        lines.append(f"- {item.label}: {item.path} ({status}{size})")
    return "\n".join(lines)


def _describe_path(label: str, path: Path) -> DiagnosticPath:
    exists = path.exists()
    size_bytes = path.stat().st_size if path.is_file() else None
    return DiagnosticPath(
        label=label,
        path=path,
        exists=exists,
        size_bytes=size_bytes,
    )
