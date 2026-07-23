"""Resolve Project Akiha runtime directories."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Filesystem locations for mutable application data."""

    data_dir: Path
    project_root: Path

    @property
    def log_dir(self) -> Path:
        """Return the directory for rotating application logs."""
        return self.data_dir / "logs"

    @property
    def state_dir(self) -> Path:
        """Return the directory for small runtime state files."""
        return self.data_dir / "state"

    @property
    def user_config_path(self) -> Path:
        """Return the mutable user config path."""
        return self.data_dir / "user_config.toml"

    @property
    def database_path(self) -> Path:
        """Return the local SQLite database path."""
        return self.data_dir / "akiha.sqlite3"

    @property
    def asset_dir(self) -> Path:
        """Return the directory for project asset files."""
        return self.project_root / "assets"


def get_app_paths(
    app_name: str = "Akiha",
    environ: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> AppPaths:
    """Build runtime paths from Windows app data conventions."""
    env = environ if environ is not None else os.environ
    base_path = env.get("LOCALAPPDATA") or env.get("APPDATA")
    if base_path is None:
        base_path = str(Path.home() / "AppData" / "Local")

    resolved_project_root = project_root or Path(__file__).resolve().parents[2]

    return AppPaths(
        data_dir=Path(base_path) / app_name,
        project_root=resolved_project_root,
    )
