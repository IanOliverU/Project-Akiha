"""Tests for typed TOML settings."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import PersonalityConfig, load_config


class SettingsTest(unittest.TestCase):
    """Verify default and overlay config behavior."""

    def test_loads_default_pet_window_config(self) -> None:
        config = load_config()

        self.assertEqual(config.pet_window.width, 180)
        self.assertEqual(config.pet_window.height, 220)
        self.assertEqual(config.pet_window.frames_per_second, 24)
        self.assertEqual(config.ai.provider, "mock")
        self.assertEqual(config.personality.character_name, "Akiha")
        self.assertIn("Akiha", config.personality.rendered_system_prompt())
        self.assertTrue(config.memory.enabled)
        self.assertEqual(config.memory.retrieval_limit, 5)

    def test_user_config_overlays_defaults(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "user_config.toml"
            config_path.write_text(
                "[pet_window]\n"
                "width = 240\n"
                "\n"
                "[ai]\n"
                'provider = "ollama"\n'
                "\n"
                "[personality]\n"
                'character_name = "Mei"\n'
                'system_prompt = "You are {character_name}."\n'
                "\n"
                "[memory]\n"
                "enabled = false\n"
                "retrieval_limit = 3\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.pet_window.width, 240)
        self.assertEqual(config.pet_window.height, 220)
        self.assertEqual(config.ai.provider, "ollama")
        self.assertEqual(config.personality.character_name, "Mei")
        self.assertEqual(config.personality.rendered_system_prompt(), "You are Mei.")
        self.assertFalse(config.memory.enabled)
        self.assertEqual(config.memory.retrieval_limit, 3)

    def test_personality_prompt_replaces_only_character_name_token(self) -> None:
        personality = PersonalityConfig(
            character_name="Aki",
            system_prompt="You are {character_name}. Keep literal braces: {json}.",
        )

        self.assertEqual(
            personality.rendered_system_prompt(),
            "You are Aki. Keep literal braces: {json}.",
        )


if __name__ == "__main__":
    unittest.main()
