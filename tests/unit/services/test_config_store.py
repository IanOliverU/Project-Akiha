"""Tests for user config persistence."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import (
    AIConfig,
    AppConfig,
    BehaviorConfig,
    MemoryConfig,
    PersonalityConfig,
    PetWindowConfig,
    load_config,
)
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
                    personality=PersonalityConfig(
                        character_name="Mei",
                        system_prompt="You are {character_name}.",
                    ),
                    memory=MemoryConfig(
                        enabled=False,
                        retrieval_limit=3,
                        require_approval=True,
                    ),
                    behavior=BehaviorConfig(
                        enabled=True,
                        proactive_enabled=True,
                        idle_after_seconds=60,
                        away_after_seconds=180,
                        minimum_seconds_between_notifications=900,
                        allow_notifications_while_away=True,
                        quiet_hours_enabled=True,
                        quiet_hours_start="23:00",
                        quiet_hours_end="08:00",
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
        self.assertEqual(config.personality.character_name, "Mei")
        self.assertEqual(config.personality.system_prompt, "You are {character_name}.")
        self.assertEqual(config.personality.rendered_system_prompt(), "You are Mei.")
        self.assertFalse(config.memory.enabled)
        self.assertEqual(config.memory.retrieval_limit, 3)
        self.assertTrue(config.memory.require_approval)
        self.assertTrue(config.behavior.enabled)
        self.assertTrue(config.behavior.proactive_enabled)
        self.assertEqual(config.behavior.idle_after_seconds, 60)
        self.assertEqual(config.behavior.away_after_seconds, 180)
        self.assertEqual(config.behavior.minimum_seconds_between_notifications, 900)
        self.assertTrue(config.behavior.allow_notifications_while_away)
        self.assertTrue(config.behavior.quiet_hours_enabled)
        self.assertEqual(config.behavior.quiet_hours_start, "23:00")
        self.assertEqual(config.behavior.quiet_hours_end, "08:00")

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

    def test_escapes_multiline_personality_prompt_for_toml(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "user_config.toml"
            store = UserConfigStore(config_path)
            store.save_config(
                AppConfig(
                    personality=PersonalityConfig(
                        character_name='Akiha "Test"',
                        system_prompt="Line one.\nLine two with {character_name}.",
                    )
                )
            )

            config = load_config(config_path)

        self.assertEqual(config.personality.character_name, 'Akiha "Test"')
        self.assertEqual(
            config.personality.system_prompt,
            "Line one.\nLine two with {character_name}.",
        )


if __name__ == "__main__":
    unittest.main()
