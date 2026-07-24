"""Tests for typed TOML settings."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import BehaviorConfig, PersonalityConfig, load_config


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
        self.assertFalse(config.memory.require_approval)
        self.assertTrue(config.behavior.enabled)
        self.assertFalse(config.behavior.proactive_enabled)
        self.assertEqual(config.behavior.idle_after_seconds, 300)
        self.assertEqual(config.behavior.away_after_seconds, 900)
        self.assertFalse(config.behavior.scheduled_check_ins_enabled)
        self.assertEqual(config.behavior.scheduled_check_in_interval_seconds, 3600)

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
                "retrieval_limit = 3\n"
                "require_approval = true\n"
                "\n"
                "[behavior]\n"
                "proactive_enabled = true\n"
                "idle_after_seconds = 60\n"
                "away_after_seconds = 120\n"
                "quiet_hours_enabled = true\n"
                'quiet_hours_start = "23:00"\n'
                'quiet_hours_end = "08:00"\n'
                "minimum_seconds_between_notifications = 600\n"
                "allow_notifications_while_away = true\n"
                "scheduled_check_ins_enabled = true\n"
                "scheduled_check_in_interval_seconds = 1200\n",
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
        self.assertTrue(config.memory.require_approval)
        self.assertTrue(config.behavior.proactive_enabled)
        self.assertEqual(config.behavior.idle_after_seconds, 60)
        self.assertEqual(config.behavior.away_after_seconds, 120)
        self.assertTrue(config.behavior.quiet_hours_enabled)
        self.assertEqual(config.behavior.quiet_hours_start, "23:00")
        self.assertEqual(config.behavior.quiet_hours_end, "08:00")
        self.assertEqual(config.behavior.minimum_seconds_between_notifications, 600)
        self.assertTrue(config.behavior.allow_notifications_while_away)
        self.assertTrue(config.behavior.scheduled_check_ins_enabled)
        self.assertEqual(config.behavior.scheduled_check_in_interval_seconds, 1200)

    def test_personality_prompt_replaces_only_character_name_token(self) -> None:
        personality = PersonalityConfig(
            character_name="Aki",
            system_prompt="You are {character_name}. Keep literal braces: {json}.",
        )

        self.assertEqual(
            personality.rendered_system_prompt(),
            "You are Aki. Keep literal braces: {json}.",
        )

    def test_behavior_config_rejects_invalid_quiet_hours(self) -> None:
        with self.assertRaises(ValueError):
            BehaviorConfig(quiet_hours_start="25:00")

    def test_behavior_config_rejects_away_threshold_before_idle(self) -> None:
        with self.assertRaises(ValueError):
            BehaviorConfig(idle_after_seconds=120, away_after_seconds=60)

    def test_behavior_config_rejects_invalid_check_in_interval(self) -> None:
        with self.assertRaises(ValueError):
            BehaviorConfig(scheduled_check_in_interval_seconds=0)


if __name__ == "__main__":
    unittest.main()
