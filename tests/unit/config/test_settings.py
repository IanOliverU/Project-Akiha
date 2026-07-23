"""Tests for typed TOML settings."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import load_config


class SettingsTest(unittest.TestCase):
    """Verify default and overlay config behavior."""

    def test_loads_default_pet_window_config(self) -> None:
        config = load_config()

        self.assertEqual(config.pet_window.width, 180)
        self.assertEqual(config.pet_window.height, 220)
        self.assertEqual(config.pet_window.frames_per_second, 24)
        self.assertEqual(config.ai.provider, "mock")

    def test_user_config_overlays_defaults(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "user_config.toml"
            config_path.write_text(
                '[pet_window]\nwidth = 240\n\n[ai]\nprovider = "ollama"\n',
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.pet_window.width, 240)
        self.assertEqual(config.pet_window.height, 220)
        self.assertEqual(config.ai.provider, "ollama")


if __name__ == "__main__":
    unittest.main()
