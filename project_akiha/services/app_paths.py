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

    @property
    def log_dir(self) -> Path:
        """Return the directory for rotating application logs."""
        return self.data_dir / "logs"

    @property
    def state_dir(self) -> Path:
        """Return the directory for small runtime state files."""
        return self.data_dir / "state"


def get_app_paths(
    app_name: str = "Akiha",
    environ: Mapping[str, str] | None = None,
) -> AppPaths:
    """Build runtime paths from Windows app data conventions."""
    env = environ if environ is not None else os.environ
    base_path = env.get("LOCALAPPDATA") or env.get("APPDATA")
    if base_path is None:
        base_path = str(Path.home() / "AppData" / "Local")

    return AppPaths(data_dir=Path(base_path) / app_name)
