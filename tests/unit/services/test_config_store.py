"""Tests for user config persistence."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.config import (
    AIConfig,
    AppConfig,
    BehaviorConfig,
    DiscordIntegrationConfig,
    ExternalIntegrationsConfig,
    GmailIntegrationConfig,
    MemoryConfig,
    PersonalityConfig,
    PetWindowConfig,
    PrivacyConfig,
    SpotifyConfig,
    VoiceConfig,
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
                        hosted_base_url="https://example.test/v1",
                        hosted_model="hosted-test",
                        request_timeout_seconds=15,
                        assistant_tools_enabled=True,
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
                    privacy=PrivacyConfig(
                        notice_version_acknowledged=1,
                        hosted_live_notice_version_acknowledged=1,
                    ),
                    behavior=BehaviorConfig(
                        enabled=True,
                        proactive_enabled=True,
                        idle_after_seconds=60,
                        away_after_seconds=180,
                        minimum_seconds_between_notifications=900,
                        allow_notifications_while_away=True,
                        scheduled_check_ins_enabled=True,
                        scheduled_check_in_interval_seconds=1200,
                        quiet_hours_enabled=True,
                        quiet_hours_start="23:00",
                        quiet_hours_end="08:00",
                    ),
                    voice=VoiceConfig(
                        enabled=True,
                        push_to_talk_enabled=True,
                        input_provider="faster-whisper",
                        input_model="medium",
                        input_language="ja",
                        input_device='USB "Microphone"',
                        output_provider="gpt-sovits",
                        output_base_url="http://localhost:9880",
                        output_voice_id="akiha",
                        output_device="Desktop speakers",
                        output_engine_auto_start=True,
                        output_engine_stop_on_exit=False,
                        automatic_speech_enabled=True,
                        proactive_speech_enabled=True,
                        english_subtitles_enabled=True,
                        export_english_subtitles_enabled=True,
                        live_transcription_enabled=True,
                        auto_stop_on_silence_enabled=True,
                        auto_send_transcript_enabled=True,
                        silence_timeout_seconds=1.5,
                        volume_percent=75,
                        speaking_rate=1.2,
                        capture_timeout_seconds=12,
                        request_timeout_seconds=10,
                        local_conversation_idle_timeout_seconds=90,
                        local_conversation_max_duration_seconds=900,
                        session_provider="gemini_live",
                        hosted_live_model="gemini-live-test",
                        hosted_live_voice_name="Aoede",
                        hosted_live_max_duration_seconds=300,
                    ),
                    spotify=SpotifyConfig(
                        enabled=True,
                        client_id="a" * 32,
                        auto_launch_desktop_app=False,
                        request_timeout_seconds=20,
                    ),
                    integrations=ExternalIntegrationsConfig(
                        visual_notifications_enabled=True,
                        voice_notifications_enabled=False,
                        notification_cooldown_seconds=2,
                        event_expiry_seconds=600,
                        receipt_retention_days=45,
                        gmail=GmailIntegrationConfig(
                            enabled=True,
                            client_id="akiha.apps.googleusercontent.com",
                            poll_interval_seconds=120,
                            notify_promotional=True,
                        ),
                        discord=DiscordIntegrationConfig(
                            enabled=True,
                            owner_user_id="789",
                            notify_authorized_channels=True,
                            authorized_channel_ids=("123", "456"),
                            reconnect_max_seconds=30,
                        ),
                    ),
                )
            )

            config = load_config(config_path)
            persisted = config_path.read_text(encoding="utf-8")

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
        self.assertEqual(config.ai.hosted_base_url, "https://example.test/v1")
        self.assertEqual(config.ai.hosted_model, "hosted-test")
        self.assertEqual(config.ai.request_timeout_seconds, 15)
        self.assertTrue(config.ai.assistant_tools_enabled)
        self.assertEqual(config.personality.character_name, "Mei")
        self.assertEqual(config.personality.system_prompt, "You are {character_name}.")
        self.assertEqual(config.personality.rendered_system_prompt(), "You are Mei.")
        self.assertFalse(config.memory.enabled)
        self.assertEqual(config.memory.retrieval_limit, 3)
        self.assertTrue(config.memory.require_approval)
        self.assertEqual(config.privacy.notice_version_acknowledged, 1)
        self.assertEqual(
            config.privacy.hosted_live_notice_version_acknowledged,
            1,
        )
        self.assertTrue(config.behavior.enabled)
        self.assertTrue(config.behavior.proactive_enabled)
        self.assertEqual(config.behavior.idle_after_seconds, 60)
        self.assertEqual(config.behavior.away_after_seconds, 180)
        self.assertEqual(config.behavior.minimum_seconds_between_notifications, 900)
        self.assertTrue(config.behavior.allow_notifications_while_away)
        self.assertTrue(config.behavior.scheduled_check_ins_enabled)
        self.assertEqual(config.behavior.scheduled_check_in_interval_seconds, 1200)
        self.assertTrue(config.behavior.quiet_hours_enabled)
        self.assertEqual(config.behavior.quiet_hours_start, "23:00")
        self.assertEqual(config.behavior.quiet_hours_end, "08:00")
        self.assertTrue(config.voice.enabled)
        self.assertTrue(config.voice.push_to_talk_enabled)
        self.assertEqual(config.voice.input_provider, "faster-whisper")
        self.assertEqual(config.voice.input_model, "medium")
        self.assertEqual(config.voice.input_language, "ja")
        self.assertEqual(config.voice.input_device, 'USB "Microphone"')
        self.assertEqual(config.voice.output_provider, "gpt-sovits")
        self.assertEqual(config.voice.output_base_url, "http://localhost:9880")
        self.assertEqual(config.voice.output_voice_id, "akiha")
        self.assertEqual(config.voice.output_device, "Desktop speakers")
        self.assertTrue(config.voice.output_engine_auto_start)
        self.assertFalse(config.voice.output_engine_stop_on_exit)
        self.assertTrue(config.voice.automatic_speech_enabled)
        self.assertTrue(config.voice.proactive_speech_enabled)
        self.assertTrue(config.voice.english_subtitles_enabled)
        self.assertTrue(config.voice.export_english_subtitles_enabled)
        self.assertTrue(config.voice.live_transcription_enabled)
        self.assertTrue(config.voice.auto_stop_on_silence_enabled)
        self.assertTrue(config.voice.auto_send_transcript_enabled)
        self.assertEqual(config.voice.silence_timeout_seconds, 1.5)
        self.assertEqual(config.voice.volume_percent, 75)
        self.assertEqual(config.voice.speaking_rate, 1.2)
        self.assertEqual(config.voice.capture_timeout_seconds, 12)
        self.assertEqual(config.voice.request_timeout_seconds, 10)
        self.assertEqual(config.voice.local_conversation_idle_timeout_seconds, 90)
        self.assertEqual(config.voice.local_conversation_max_duration_seconds, 900)
        self.assertEqual(config.voice.session_provider, "gemini_live")
        self.assertEqual(config.voice.hosted_live_model, "gemini-live-test")
        self.assertEqual(config.voice.hosted_live_voice_name, "Aoede")
        self.assertEqual(config.voice.hosted_live_max_duration_seconds, 300)
        self.assertTrue(config.spotify.enabled)
        self.assertEqual(config.spotify.client_id, "a" * 32)
        self.assertFalse(config.spotify.auto_launch_desktop_app)
        self.assertEqual(config.spotify.request_timeout_seconds, 20)
        self.assertFalse(config.integrations.voice_notifications_enabled)
        self.assertEqual(config.integrations.notification_cooldown_seconds, 2)
        self.assertEqual(config.integrations.event_expiry_seconds, 600)
        self.assertEqual(config.integrations.receipt_retention_days, 45)
        self.assertTrue(config.integrations.gmail.enabled)
        self.assertEqual(config.integrations.gmail.poll_interval_seconds, 120)
        self.assertTrue(config.integrations.gmail.notify_promotional)
        self.assertTrue(config.integrations.discord.enabled)
        self.assertEqual(config.integrations.discord.owner_user_id, "789")
        self.assertEqual(
            config.integrations.discord.authorized_channel_ids,
            ("123", "456"),
        )
        self.assertNotIn("refresh_token", persisted)
        self.assertNotIn("bot_token", persisted)

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
