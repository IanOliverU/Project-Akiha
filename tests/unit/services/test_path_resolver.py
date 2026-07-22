"""Tests for config path resolution."""

from __future__ import annotations

import unittest
from pathlib import Path

from project_akiha.services.path_resolver import ConfigPathResolver


class ConfigPathResolverTest(unittest.TestCase):
    """Verify configured paths resolve against the intended roots."""

    def test_absolute_path_is_returned_unchanged(self) -> None:
        resolver = ConfigPathResolver(
            project_root=Path("C:/Project Akiha"),
            asset_dir=Path("C:/Project Akiha/assets"),
        )

        resolved_path = resolver.resolve_asset_path("C:/Sprites/manifest.toml")

        self.assertEqual(resolved_path, Path("C:/Sprites/manifest.toml"))

    def test_assets_prefixed_path_resolves_from_project_root(self) -> None:
        resolver = ConfigPathResolver(
            project_root=Path("C:/Project Akiha"),
            asset_dir=Path("C:/Project Akiha/assets"),
        )

        resolved_path = resolver.resolve_asset_path("assets/animations/manifest.toml")

        self.assertEqual(
            resolved_path,
            Path("C:/Project Akiha/assets/animations/manifest.toml"),
        )

    def test_asset_relative_path_resolves_from_asset_dir(self) -> None:
        resolver = ConfigPathResolver(
            project_root=Path("C:/Project Akiha"),
            asset_dir=Path("C:/Project Akiha/assets"),
        )

        resolved_path = resolver.resolve_asset_path("animations/manifest.toml")

        self.assertEqual(
            resolved_path,
            Path("C:/Project Akiha/assets/animations/manifest.toml"),
        )


if __name__ == "__main__":
    unittest.main()
