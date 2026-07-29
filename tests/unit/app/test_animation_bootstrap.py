"""Tests for animation provider startup fallback behavior."""

from __future__ import annotations

import logging
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.app.main import _build_animation_provider
from project_akiha.providers.animation import (
    AssetAnimationProvider,
    PlaceholderAnimationProvider,
)


class AnimationBootstrapTest(unittest.TestCase):
    """Verify startup animation loading fails over cleanly."""

    def test_uses_placeholder_when_manifest_is_missing(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "missing.toml"

            provider = _build_animation_provider(
                manifest_path,
                logging.getLogger("test_missing_animation_manifest"),
            )

        self.assertIsInstance(provider, PlaceholderAnimationProvider)

    def test_uses_placeholder_when_manifest_references_missing_sprite(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            manifest_path.write_text(
                "[animations.idle]\n" 'frames = ["idle/missing.png"]\n',
                encoding="utf-8",
            )
            logger = logging.getLogger("test_missing_sprite")

            with self.assertLogs(logger, level="WARNING") as captured:
                provider = _build_animation_provider(manifest_path, logger)

        self.assertIsInstance(provider, PlaceholderAnimationProvider)
        self.assertIn("Animation manifest failed to load", captured.output[0])

    def test_uses_asset_provider_when_manifest_and_sprite_exist(self) -> None:
        with TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "manifest.toml"
            sprite_path = Path(directory) / "idle" / "000.png"
            sprite_path.parent.mkdir(parents=True)
            sprite_path.touch()
            manifest_path.write_text(
                "[animations.idle]\n" 'frames = ["idle/000.png"]\n',
                encoding="utf-8",
            )

            provider = _build_animation_provider(
                manifest_path,
                logging.getLogger("test_valid_sprite"),
            )

        self.assertIsInstance(provider, AssetAnimationProvider)


if __name__ == "__main__":
    unittest.main()
