"""Tests for user config persistence."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import AIConfig, AppConfig, PetWindowConfig, load_config
from project_akiha.services.config_store import UserConfigStore


class UserConfigStoreTest(unittest.TestCase):
    """Verify config overrides are saved as loadable TOML."""

    def test_saves_config_that_can_be_loaded_as_overlay(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "user_config.toml"
            store = UserConfigStore(config_path)
            store.save_config(
                AppConfig(
                    pet_window=PetWindowConfig(
                        width=240,
                        height=260,
                        frames_per_second=30,
                        start_x=50,
                        start_y=60,
                        always_on_top=False,
                        animation_manifest_path="assets/custom/manifest.toml",
                        walking_speed_pixels=5,
                    ),
                    ai=AIConfig(
                        provider="ollama",
                        ollama_base_url="http://localhost:11434",
                        ollama_model="akiha-test",
                        request_timeout_seconds=15,
                    ),
                )
            )

            config = load_config(config_path)

        self.assertEqual(config.pet_window.width, 240)
        self.assertEqual(config.pet_window.height, 260)
        self.assertEqual(config.pet_window.frames_per_second, 30)
        self.assertEqual(config.pet_window.start_x, 50)
        self.assertEqual(config.pet_window.start_y, 60)
        self.assertFalse(config.pet_window.always_on_top)
        self.assertEqual(config.pet_window.walking_speed_pixels, 5)
        self.assertEqual(
            config.pet_window.animation_manifest_path,
            "assets/custom/manifest.toml",
        )
        self.assertEqual(config.ai.provider, "ollama")
        self.assertEqual(config.ai.ollama_model, "akiha-test")
        self.assertEqual(config.ai.request_timeout_seconds, 15)

    def test_escapes_manifest_path_for_toml(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "user_config.toml"
            store = UserConfigStore(config_path)
            store.save_config(
                AppConfig(
                    pet_window=PetWindowConfig(
                        animation_manifest_path='C:\\Akiha "Sprites"\\manifest.toml'
                    )
                )
            )

            config = load_config(config_path)

        self.assertEqual(
            config.pet_window.animation_manifest_path,
            'C:\\Akiha "Sprites"\\manifest.toml',
        )


if __name__ == "__main__":
    unittest.main()
