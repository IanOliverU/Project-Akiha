"""Tests for typed TOML settings."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import (
    AIConfig,
    BehaviorConfig,
    PersonalityConfig,
    VoiceConfig,
    load_config,
)


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
        self.assertFalse(config.voice.enabled)
        self.assertTrue(config.voice.push_to_talk_enabled)
        self.assertEqual(config.voice.input_provider, "faster-whisper")
        self.assertEqual(config.voice.output_provider, "voicevox")
        self.assertFalse(config.voice.automatic_speech_enabled)
        self.assertEqual(config.voice.capture_timeout_seconds, 30)
        self.assertFalse(config.voice.input_enabled)
        self.assertFalse(config.voice.output_enabled)

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
                "scheduled_check_in_interval_seconds = 1200\n"
                "\n"
                "[voice]\n"
                "enabled = true\n"
                "push_to_talk_enabled = false\n"
                'input_provider = "disabled"\n'
                'input_model = "medium"\n'
                'input_language = "ja"\n'
                'input_device = "Test microphone"\n'
                'output_provider = "voicevox"\n'
                'output_base_url = "http://localhost:50021"\n'
                'output_voice_id = "14"\n'
                'output_device = "Test speakers"\n'
                "automatic_speech_enabled = true\n"
                "volume_percent = 75\n"
                "speaking_rate = 1.2\n"
                "capture_timeout_seconds = 12\n"
                "request_timeout_seconds = 10\n",
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
        self.assertTrue(config.voice.enabled)
        self.assertFalse(config.voice.push_to_talk_enabled)
        self.assertEqual(config.voice.input_provider, "disabled")
        self.assertEqual(config.voice.input_model, "medium")
        self.assertEqual(config.voice.input_language, "ja")
        self.assertEqual(config.voice.input_device, "Test microphone")
        self.assertEqual(config.voice.output_provider, "voicevox")
        self.assertEqual(config.voice.output_base_url, "http://localhost:50021")
        self.assertEqual(config.voice.output_voice_id, "14")
        self.assertEqual(config.voice.output_device, "Test speakers")
        self.assertTrue(config.voice.automatic_speech_enabled)
        self.assertEqual(config.voice.volume_percent, 75)
        self.assertEqual(config.voice.speaking_rate, 1.2)
        self.assertEqual(config.voice.capture_timeout_seconds, 12)
        self.assertEqual(config.voice.request_timeout_seconds, 10)
        self.assertFalse(config.voice.input_enabled)
        self.assertTrue(config.voice.output_enabled)

    def test_user_config_accepts_utf8_bom(self) -> None:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "user_config.toml"
            config_path.write_text(
                "\ufeff[personality]\n" 'character_name = "Mei"\n',
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.personality.character_name, "Mei")

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

    def test_ai_config_rejects_non_http_ollama_url(self) -> None:
        with self.assertRaises(ValueError):
            AIConfig(ollama_base_url="file:///tmp/ollama.sock")

    def test_ai_config_rejects_ollama_url_without_host(self) -> None:
        with self.assertRaises(ValueError):
            AIConfig(ollama_base_url="http:///api")

    def test_voice_config_exposes_enabled_provider_paths(self) -> None:
        voice = VoiceConfig(enabled=True)

        self.assertTrue(voice.input_enabled)
        self.assertTrue(voice.output_enabled)

    def test_voice_config_rejects_unknown_provider(self) -> None:
        with self.assertRaises(ValueError):
            VoiceConfig(input_provider="cloud-microphone")

        with self.assertRaises(ValueError):
            VoiceConfig(output_provider="cloud-speaker")

    def test_voice_config_rejects_invalid_output_url(self) -> None:
        with self.assertRaises(ValueError):
            VoiceConfig(output_base_url="file:///voicevox")

        with self.assertRaises(ValueError):
            VoiceConfig(output_base_url="http:///voicevox")

    def test_voice_config_rejects_invalid_playback_values(self) -> None:
        with self.assertRaises(ValueError):
            VoiceConfig(volume_percent=101)

        with self.assertRaises(ValueError):
            VoiceConfig(speaking_rate=0.25)

        with self.assertRaises(ValueError):
            VoiceConfig(capture_timeout_seconds=0)

        with self.assertRaises(ValueError):
            VoiceConfig(request_timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
