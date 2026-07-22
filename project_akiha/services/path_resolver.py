"""Resolve configured file paths into concrete filesystem locations."""

from __future__ import annotations

from pathlib import Path


class ConfigPathResolver:
    """Resolve user-configured paths against known application roots."""

    def __init__(self, project_root: Path, asset_dir: Path) -> None:
        self._project_root = project_root
        self._asset_dir = asset_dir

    def resolve_asset_path(self, path_value: str) -> Path:
        """Resolve an asset path from config to an absolute path."""
        configured_path = Path(path_value)
        if configured_path.is_absolute():
            return configured_path

        if configured_path.parts and configured_path.parts[0] == "assets":
            return self._project_root / configured_path

        return self._asset_dir / configured_path
