"""Tests for the settings window."""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QTimeEdit,
)

import project_akiha.ui.settings_window as settings_window_module
from project_akiha.config import (
    AIConfig,
    AppConfig,
    PrivacyConfig,
    SpotifyConfig,
    VoiceConfig,
)
from project_akiha.core.actions import (
    ApprovedDirectory,
    InstalledApplication,
    PermissionGrant,
)
from project_akiha.integrations.spotify.auth import SpotifyToken
from project_akiha.services.ai_provider_discovery import (
    AIProviderDiscoveryResult,
)
from project_akiha.services.pet_diagnostics import PetDiagnosticsSnapshot
from project_akiha.ui.settings_window import SettingsWindow
from project_akiha.ui.theme import AKIHA_PALETTE


class _CredentialStore:
    def __init__(self) -> None:
        self.secrets: dict[str, str] = {}

    def get_secret(self, provider: str) -> str | None:
        return self.secrets.get(provider)

    def set_secret(self, provider: str, secret: str) -> None:
        self.secrets[provider] = secret

    def delete_secret(self, provider: str) -> None:
        self.secrets.pop(provider, None)

    def get_named_secret(self, namespace: str, name: str) -> str | None:
        return self.secrets.get(f"{namespace}:{name}")

    def set_named_secret(self, namespace: str, name: str, secret: str) -> None:
        self.secrets[f"{namespace}:{name}"] = secret

    def delete_named_secret(self, namespace: str, name: str) -> None:
        self.secrets.pop(f"{namespace}:{name}", None)


class SettingsWindowTest(unittest.TestCase):
    """Verify settings controls emit updated app config."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_saves_behavior_controls(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)

            window._proactive_enabled_input.setChecked(True)
            window._idle_after_input.setValue(2)
            window._away_after_input.setValue(4)
            window._notification_cooldown_input.setValue(10)
            window._allow_notifications_while_away_input.setChecked(True)
            window._scheduled_check_ins_enabled_input.setChecked(True)
            window._scheduled_check_in_interval_input.setValue(20)
            window._quiet_hours_enabled_input.setChecked(True)
            window._quiet_hours_start_input.setTime(QTime(21, 30))
            window._quiet_hours_end_input.setTime(QTime(8, 15))

            window._save()

        self.assertEqual(len(emitted), 1)
        self.assertTrue(emitted[0].behavior.proactive_enabled)
        self.assertEqual(emitted[0].behavior.idle_after_seconds, 120)
        self.assertEqual(emitted[0].behavior.away_after_seconds, 240)
        self.assertEqual(
            emitted[0].behavior.minimum_seconds_between_notifications,
            600,
        )
        self.assertTrue(emitted[0].behavior.allow_notifications_while_away)
        self.assertTrue(emitted[0].behavior.scheduled_check_ins_enabled)
        self.assertEqual(emitted[0].behavior.scheduled_check_in_interval_seconds, 1200)
        self.assertTrue(emitted[0].behavior.quiet_hours_enabled)
        self.assertEqual(emitted[0].behavior.quiet_hours_start, "21:30")
        self.assertEqual(emitted[0].behavior.quiet_hours_end, "08:15")

    def test_saves_discord_owner_notification_controls(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)
            window._integration_cooldown_input.setValue(0)
            window._discord_owner_user_id_input.setText("123456789")
            window._discord_notify_owner_mentions_input.setChecked(True)
            window._discord_notify_owner_replies_input.setChecked(True)

            window._save()

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].integrations.notification_cooldown_seconds, 0)
        self.assertEqual(
            emitted[0].integrations.discord.owner_user_id,
            "123456789",
        )
        self.assertTrue(emitted[0].integrations.discord.notify_owner_mentions)
        self.assertTrue(emitted[0].integrations.discord.notify_owner_replies)

    def test_uniform_theme_and_sections_are_applied(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

        section_titles = {
            section.title()
            for section in window.findChildren(QGroupBox)
            if section.objectName() == "settingsSection"
        }
        self.assertEqual(window.objectName(), "akihaSettingsWindow")
        self.assertEqual(window._tabs.count(), 8)
        self.assertEqual(
            [button.text() for button in window._settings_nav_buttons],
            [
                "Pet",
                "AI",
                "Memory",
                "Behavior",
                "Actions",
                "Spotify",
                "Integrations",
                "Voice",
            ],
        )
        self.assertTrue(window._settings_nav_buttons[0].isChecked())
        self.assertTrue(
            all(not button.icon().isNull() for button in window._settings_nav_buttons)
        )
        window._settings_nav_buttons[3].click()
        self.assertEqual(window._tabs.currentIndex(), 3)
        self.assertTrue(window._settings_nav_buttons[3].isChecked())
        self.assertEqual(window._save_button.objectName(), "primaryButton")
        self.assertEqual(window._save_button.text(), "Save Changes")
        self.assertEqual(window._settings_title.text(), "Akiha")
        self.assertTrue(
            all(
                combo.objectName() == "settingsComboBox"
                for combo in window.findChildren(QComboBox)
            )
        )
        steppers = (
            window.findChildren(QSpinBox)
            + window.findChildren(QDoubleSpinBox)
            + window.findChildren(QTimeEdit)
        )
        self.assertTrue(steppers)
        self.assertTrue(
            all(stepper.objectName() == "settingsStepper" for stepper in steppers)
        )
        previous_fps = window._fps_input.value()
        window._fps_input.stepUp()
        self.assertEqual(window._fps_input.value(), previous_fps + 1)
        window._fps_input.stepDown()
        self.assertEqual(window._fps_input.value(), previous_fps)
        self.assertEqual(window._memory_enabled_input.objectName(), "settingsToggle")
        self.assertIn(AKIHA_PALETTE.window, window.styleSheet())
        self.assertIn(AKIHA_PALETTE.primary, window.styleSheet())
        self.assertTrue(
            {
                "Window",
                "Appearance",
                "Care system",
                "Provider",
                "Processing boundary",
                "Identity",
                "Memory",
                "Awareness",
                "Proactive behavior",
                "Permission controls",
                "Approved directories",
                "Allowlisted applications",
                "Spotify account",
                "Playback",
                "Listening",
                "Speaking",
                "Subtitles",
                "Diagnostics",
            }.issubset(section_titles)
        )

    def test_pet_diagnostics_controls_present_typed_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            requested: list[str] = []
            window.pet_diagnostics_requested.connect(
                lambda: requested.append("diagnostics")
            )
            snapshot = PetDiagnosticsSnapshot(
                revision=3,
                evaluated_at=datetime(2026, 8, 18, 12, 0, tzinfo=UTC),
                satiety=80,
                energy=70,
                attention=60,
                affection=55,
                xp=30,
                level=2,
                currency=8,
                decay_remainders=(10, 20, 30),
            )

            window._pet_diagnostics_button.click()
            window.set_pet_diagnostics(snapshot)

        self.assertEqual(requested, ["diagnostics"])
        self.assertEqual(window._pet_diagnostic_status.text(), "Pet state is ready.")
        self.assertIn("Satiety 80%", window._pet_state_summary.text())
        self.assertEqual(
            window._pet_progression_summary.text(),
            "Level 2 | 30 XP | 8 currency",
        )
        self.assertIn("Revision 3", window._pet_runtime_summary.text())

    def test_pet_reset_requires_explicit_confirmation(self) -> None:
        original_question = settings_window_module.QMessageBox.question
        try:
            with TemporaryDirectory() as directory:
                window = SettingsWindow(AppConfig(), log_dir=Path(directory))
                requested: list[str] = []
                window.pet_reset_requested.connect(lambda: requested.append("reset"))
                settings_window_module.QMessageBox.question = lambda *args: (
                    settings_window_module.QMessageBox.StandardButton.No
                )
                window._pet_reset_button.click()
                self.assertEqual(requested, [])

                settings_window_module.QMessageBox.question = lambda *args: (
                    settings_window_module.QMessageBox.StandardButton.Yes
                )
                window._pet_reset_button.click()
        finally:
            settings_window_module.QMessageBox.question = original_question

        self.assertEqual(requested, ["reset"])

    def test_pet_maintenance_busy_state_blocks_overlapping_requests(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            window.set_pet_maintenance_busy(True)

            self.assertFalse(window._pet_diagnostics_button.isEnabled())
            self.assertFalse(window._pet_reset_button.isEnabled())
            self.assertEqual(
                window._pet_diagnostic_status.text(),
                "Checking pet state...",
            )

    def test_assistant_permission_controls_refresh_and_emit_actions(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            directory_requests: list[tuple[str, bool, bool]] = []
            application_requests: list[str] = []
            close_requests: list[str] = []
            window.assistant_directory_approval_requested.connect(
                lambda root, search, open_files: directory_requests.append(
                    (root, search, open_files)
                )
            )
            window.assistant_application_grant_requested.connect(
                application_requests.append
            )
            window.assistant_application_close_grant_requested.connect(
                close_requests.append
            )
            approved = ApprovedDirectory(
                root=str(Path(directory).resolve()),
                search_permission_id=1,
                open_permission_id=None,
                is_available=True,
            )
            window.update_assistant_permissions(
                (approved,),
                (
                    InstalledApplication(
                        "chrome",
                        "Google Chrome",
                        Path("chrome.exe"),
                    ),
                ),
                (
                    PermissionGrant(
                        id=2,
                        capability="applications.launch",
                        target="chrome",
                        created_at="2026-07-31T00:00:00+00:00",
                    ),
                    PermissionGrant(
                        id=3,
                        capability="applications.close",
                        target="chrome",
                        created_at="2026-07-31T00:00:00+00:00",
                    ),
                    PermissionGrant(
                        id=4,
                        capability="spotify.playback",
                        target="spotify",
                        created_at="2026-07-31T00:00:00+00:00",
                    ),
                ),
            )

            window._assistant_directory_list.setCurrentRow(0)
            window._assistant_directory_open_input.setChecked(True)
            window._apply_assistant_directory()
            window._assistant_application_list.setCurrentRow(0)
            window._enable_assistant_application()
            window._enable_assistant_application_close()

        self.assertEqual(
            directory_requests,
            [(str(Path(directory).resolve()), True, True)],
        )
        self.assertEqual(application_requests, ["chrome"])
        self.assertEqual(close_requests, ["chrome"])
        self.assertIn(
            "Google Chrome", window._assistant_application_list.item(0).text()
        )
        self.assertIn(
            "launch on, close on",
            window._assistant_application_list.item(0).text(),
        )
        self.assertEqual(window._spotify_playback_permission_status.text(), "Enabled")

    def test_saves_ai_assistant_tool_opt_in(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)
            window._assistant_tools_enabled_input.setChecked(True)

            window._save()

        self.assertTrue(emitted[0].ai.assistant_tools_enabled)

    def test_saves_spotify_public_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)
            window._spotify_enabled_input.setChecked(True)
            window._spotify_client_id_input.setText("a" * 32)
            window._spotify_auto_launch_input.setChecked(False)
            window._spotify_timeout_input.setValue(22)

            saved = window._save()

        self.assertTrue(saved)
        self.assertTrue(emitted[0].spotify.enabled)
        self.assertEqual(emitted[0].spotify.client_id, "a" * 32)
        self.assertFalse(emitted[0].spotify.auto_launch_desktop_app)
        self.assertEqual(emitted[0].spotify.request_timeout_seconds, 22)

    def test_gmail_client_secret_is_a_password_field_not_public_config(self) -> None:
        credentials = _CredentialStore()
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                AppConfig(),
                log_dir=Path(directory),
                credential_store=credentials,
            )

        self.assertEqual(
            window._gmail_client_secret_input.echoMode(),
            QLineEdit.EchoMode.Password,
        )
        self.assertFalse(hasattr(window._config.integrations.gmail, "client_secret"))

    def test_spotify_refresh_token_is_saved_separately(self) -> None:
        credentials = _CredentialStore()
        config = AppConfig().with_spotify(
            SpotifyConfig(enabled=True, client_id="a" * 32)
        )
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                config,
                log_dir=Path(directory),
                credential_store=credentials,
            )
            window._handle_spotify_authorization_ready(
                SpotifyToken(
                    access_token="memory-only-access",
                    refresh_token="saved-refresh",
                    expires_at=1000.0,
                    scopes=("user-library-read",),
                )
            )

        self.assertEqual(
            credentials.secrets["spotify:refresh_token"],
            "saved-refresh",
        )
        self.assertNotIn("memory-only-access", credentials.secrets.values())
        self.assertEqual(
            window._spotify_connection_status.text(),
            "Spotify connected securely.",
        )

    def test_saved_spotify_authorization_is_shown_on_startup(self) -> None:
        credentials = _CredentialStore()
        credentials.secrets["spotify:refresh_token"] = "saved-refresh"

        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                AppConfig(),
                log_dir=Path(directory),
                credential_store=credentials,
            )

        self.assertEqual(
            window._spotify_connection_status.text(),
            "Spotify connected securely.",
        )

    def test_behavior_away_minimum_stays_after_idle(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            window._idle_after_input.setValue(12)

        self.assertEqual(window._away_after_input.minimum(), 13)

    def test_saves_hosted_provider_and_api_key_separately(self) -> None:
        credentials = _CredentialStore()
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                AppConfig(),
                log_dir=Path(directory),
                credential_store=credentials,
            )
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)

            window._ai_provider_input.setCurrentText("gemini")
            window._hosted_model_input.setText("gemini-test")
            window._ai_api_key_input.setText("secret-api-key")
            window._save()

        self.assertEqual(emitted[0].ai.provider, "gemini")
        self.assertEqual(emitted[0].ai.hosted_model, "gemini-test")
        self.assertEqual(credentials.secrets["gemini"], "secret-api-key")
        self.assertFalse(hasattr(emitted[0].ai, "api_key"))
        self.assertEqual(window._ai_api_key_input.text(), "")
        self.assertEqual(window._ai_api_key_status.text(), "API key saved securely")

    def test_ai_processing_boundary_follows_selected_provider(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            self.assertEqual(
                window._processing_mode_value.text(),
                "Fully Local Modular",
            )
            self.assertEqual(
                window._text_processing_value.text(),
                "Local device only",
            )
            self.assertEqual(
                window._audio_processing_value.text(),
                "Local device only",
            )

            window._ai_provider_input.setCurrentText("gemini")

        self.assertEqual(
            window._processing_mode_value.text(),
            "Hybrid API Modular",
        )
        self.assertEqual(
            window._text_processing_value.text(),
            "Off-device provider endpoint",
        )
        self.assertEqual(
            window._audio_processing_value.text(),
            "Local device only",
        )

    def test_compatible_endpoint_boundary_updates_between_local_and_remote(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            window._ai_provider_input.setCurrentText("openai-compatible")

            self.assertEqual(
                window._processing_mode_value.text(),
                "Fully Local Modular",
            )

            window._hosted_base_url_input.setText("https://example.test/v1")

        self.assertEqual(
            window._processing_mode_value.text(),
            "Hybrid API Modular",
        )
        self.assertEqual(
            window._text_processing_value.text(),
            "Off-device provider endpoint",
        )

    def test_remote_ollama_endpoint_is_disclosed_as_off_device(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            window._ai_provider_input.setCurrentText("ollama")
            window._ollama_base_url_input.setText("http://192.168.1.20:11434")

        self.assertEqual(
            window._processing_mode_value.text(),
            "Hybrid API Modular",
        )
        self.assertEqual(
            window._text_processing_value.text(),
            "Off-device provider endpoint",
        )

    def test_clear_hosted_api_key(self) -> None:
        credentials = _CredentialStore()
        credentials.secrets["gemini"] = "secret-api-key"
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                AppConfig(),
                log_dir=Path(directory),
                credential_store=credentials,
            )
            window._ai_provider_input.setCurrentText("gemini")

            window._clear_ai_api_key()

        self.assertNotIn("gemini", credentials.secrets)
        self.assertEqual(window._ai_api_key_status.text(), "No API key saved")

    def test_selecting_grok_applies_xai_defaults(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            window._ai_provider_input.setCurrentText("grok")

        self.assertEqual(
            window._hosted_base_url_input.text(),
            "https://api.x.ai/v1",
        )
        self.assertEqual(window._hosted_model_input.text(), "grok-4.5")

    def test_discovered_models_populate_grok_model_selector(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            window._ai_provider_input.setCurrentText("grok")

            window._handle_ai_models_ready(
                AIProviderDiscoveryResult(
                    provider="grok",
                    models=("grok-4.3", "grok-4.5"),
                )
            )

        self.assertEqual(window._hosted_model_input.count(), 2)
        self.assertEqual(window._hosted_model_input.text(), "grok-4.5")
        self.assertEqual(
            window._ai_connection_status.text(),
            "Connected. Found 2 models.",
        )

    def test_api_key_in_model_field_is_rejected_before_save(self) -> None:
        credentials = _CredentialStore()
        config = AppConfig().with_ai(
            AIConfig(
                provider="grok",
                hosted_base_url="https://api.x.ai/v1",
                hosted_model="grok-4.5",
            )
        )
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                config,
                log_dir=Path(directory),
                credential_store=credentials,
            )
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)
            window._hosted_model_input.setText("xai-" + ("a" * 40))
            window._ai_api_key_input.setText("new-secret")

            window._save()

        self.assertEqual(emitted, [])
        self.assertEqual(credentials.secrets, {})
        self.assertIn(
            "appears to contain an API key",
            window._ai_connection_status.text(),
        )

    def test_saves_voice_controls(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                AppConfig(
                    privacy=PrivacyConfig(notice_version_acknowledged=1),
                ),
                log_dir=Path(directory),
            )
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)

            window._voice_enabled_input.setChecked(True)
            window._automatic_speech_enabled_input.setChecked(True)
            window._proactive_speech_enabled_input.setChecked(True)
            window._english_subtitles_enabled_input.setChecked(True)
            window._export_english_subtitles_enabled_input.setChecked(True)
            window._live_transcription_enabled_input.setChecked(True)
            window._auto_stop_on_silence_enabled_input.setChecked(True)
            window._auto_send_transcript_enabled_input.setChecked(True)
            window._voice_silence_timeout_input.setValue(1.5)
            window._voice_input_model_input.setText("medium")
            window._voice_input_language_input.setCurrentText("ja")
            window._voice_input_device_input.setCurrentText("USB microphone")
            window._voice_output_provider_input.setCurrentText("gpt-sovits")
            window._voice_output_base_url_input.setText("http://localhost:9880")
            window._voice_output_voice_id_input.setText("akiha")
            window._voice_output_device_input.setCurrentText("Desktop speakers")
            window._voice_output_engine_auto_start_input.setChecked(True)
            window._voice_output_engine_stop_on_exit_input.setChecked(False)
            window._voice_volume_input.setValue(75)
            window._voice_speaking_rate_input.setValue(1.2)
            window._voice_capture_timeout_input.setValue(12)
            window._voice_request_timeout_input.setValue(10)
            window._voice_conversation_idle_timeout_input.setValue(90)
            window._voice_conversation_duration_input.setValue(15)

            window._save()

        voice = emitted[0].voice
        self.assertTrue(voice.enabled)
        self.assertTrue(voice.automatic_speech_enabled)
        self.assertTrue(voice.proactive_speech_enabled)
        self.assertTrue(voice.english_subtitles_enabled)
        self.assertTrue(voice.export_english_subtitles_enabled)
        self.assertTrue(voice.live_transcription_enabled)
        self.assertTrue(voice.auto_stop_on_silence_enabled)
        self.assertTrue(voice.auto_send_transcript_enabled)
        self.assertEqual(voice.silence_timeout_seconds, 1.5)
        self.assertEqual(voice.input_provider, "faster-whisper")
        self.assertEqual(voice.input_model, "medium")
        self.assertEqual(voice.input_language, "ja")
        self.assertEqual(voice.input_device, "USB microphone")
        self.assertEqual(voice.output_provider, "gpt-sovits")
        self.assertEqual(voice.output_base_url, "http://localhost:9880")
        self.assertEqual(voice.output_voice_id, "akiha")
        self.assertEqual(voice.output_device, "Desktop speakers")
        self.assertTrue(voice.output_engine_auto_start)
        self.assertFalse(voice.output_engine_stop_on_exit)
        self.assertEqual(voice.volume_percent, 75)
        self.assertEqual(voice.speaking_rate, 1.2)
        self.assertEqual(voice.capture_timeout_seconds, 12)
        self.assertEqual(voice.request_timeout_seconds, 10)
        self.assertEqual(voice.local_conversation_idle_timeout_seconds, 90)
        self.assertEqual(voice.local_conversation_max_duration_seconds, 900)
        self.assertEqual(emitted[0].privacy.notice_version_acknowledged, 1)

    def test_saves_acknowledged_hosted_live_controls(self) -> None:
        config = AppConfig(
            privacy=PrivacyConfig(hosted_live_notice_version_acknowledged=1),
            voice=VoiceConfig(enabled=True),
        )
        with TemporaryDirectory() as directory:
            window = SettingsWindow(config, log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)
            window._set_voice_session_provider("gemini_live")
            window._hosted_live_model_input.setText("gemini-live-test")
            window._hosted_live_voice_input.setCurrentText("Aoede")
            window._set_hosted_live_duration(300)

            saved = window._save()

        self.assertTrue(saved)
        self.assertEqual(emitted[0].voice.session_provider, "gemini_live")
        self.assertEqual(emitted[0].voice.hosted_live_model, "gemini-live-test")
        self.assertEqual(emitted[0].voice.hosted_live_voice_name, "Aoede")
        self.assertEqual(emitted[0].voice.hosted_live_max_duration_seconds, 300)
        self.assertIn("Google Gemini", window._audio_processing_value.text())

    def test_hosted_live_save_stops_when_notice_is_declined(self) -> None:
        credentials = _CredentialStore()
        with TemporaryDirectory() as directory:
            window = SettingsWindow(
                AppConfig(voice=VoiceConfig(enabled=True)),
                log_dir=Path(directory),
                credential_store=credentials,
            )
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)
            window._ai_provider_input.setCurrentText("gemini")
            window._ai_api_key_input.setText("not-persisted")
            window._set_voice_session_provider("gemini_live")
            window._review_hosted_live_privacy_notice = lambda: False

            saved = window._save()

        self.assertFalse(saved)
        self.assertEqual(emitted, [])
        self.assertEqual(credentials.secrets, {})
        self.assertIn("required", window._hosted_live_health_status.text())

    def test_voice_controls_follow_master_switch(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            self.assertFalse(window._automatic_speech_enabled_input.isEnabled())
            self.assertFalse(window._proactive_speech_enabled_input.isEnabled())
            self.assertFalse(window._english_subtitles_enabled_input.isEnabled())
            self.assertFalse(window._export_english_subtitles_enabled_input.isEnabled())
            self.assertFalse(window._live_transcription_enabled_input.isEnabled())
            self.assertFalse(window._voice_output_engine_auto_start_input.isEnabled())
            self.assertFalse(window._voice_session_provider_input.isEnabled())
            window._voice_enabled_input.setChecked(True)

        self.assertTrue(window._automatic_speech_enabled_input.isEnabled())
        self.assertTrue(window._proactive_speech_enabled_input.isEnabled())
        self.assertTrue(window._english_subtitles_enabled_input.isEnabled())
        self.assertTrue(window._export_english_subtitles_enabled_input.isEnabled())
        self.assertTrue(window._live_transcription_enabled_input.isEnabled())
        self.assertTrue(window._voice_output_base_url_input.isEnabled())
        window._voice_output_provider_input.setCurrentText("gpt-sovits")
        self.assertTrue(window._voice_output_engine_auto_start_input.isEnabled())
        self.assertTrue(window._voice_session_provider_input.isEnabled())
        self.assertFalse(window._hosted_live_model_input.isEnabled())
        window._set_voice_session_provider("gemini_live")
        self.assertTrue(window._hosted_live_model_input.isEnabled())
        window._voice_output_engine_auto_start_input.setChecked(True)

    def test_voice_diagnostic_actions_and_results_are_presented(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            requested: list[str] = []
            window.voice_health_check_requested.connect(
                lambda: requested.append("health")
            )
            window.voice_microphone_test_requested.connect(
                lambda: requested.append("microphone")
            )
            window.voice_output_test_requested.connect(
                lambda: requested.append("output")
            )
            window._voice_enabled_input.setChecked(True)

            window._voice_health_check_button.click()
            window._voice_microphone_test_button.click()
            window._voice_output_test_button.click()
            window.set_voice_health(
                "available",
                "Whisper ready.",
                "unavailable",
                "GPT-SoVITS is not running.",
            )
            window.set_voice_diagnostic_status("Needs attention.", True)
            window.set_voice_test_active("microphone", True)

        self.assertEqual(requested, ["health", "microphone", "output"])
        self.assertIn("Whisper ready.", window._voice_input_health.text())
        self.assertIn("GPT-SoVITS is not running.", window._voice_output_health.text())
        self.assertEqual(window._voice_diagnostic_status.text(), "Needs attention.")
        self.assertEqual(
            window._voice_microphone_test_button.text(),
            "Stop microphone test",
        )

    def test_system_default_devices_save_as_empty_names(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)

            window._voice_enabled_input.setChecked(True)
            window._save()

        self.assertEqual(emitted[0].voice.input_device, "")
        self.assertEqual(emitted[0].voice.output_device, "")

    def test_open_directory_creates_path_and_opens_url(self) -> None:
        opened_urls: list[str] = []

        class FakeDesktopServices:
            @staticmethod
            def openUrl(url: object) -> bool:
                opened_urls.append(url.toLocalFile())
                return True

        original_desktop_services = settings_window_module.QDesktopServices
        settings_window_module.QDesktopServices = FakeDesktopServices
        try:
            with TemporaryDirectory() as directory:
                target = Path(directory) / "Akiha" / "logs"

                result = settings_window_module._open_directory(target)

                self.assertTrue(result)
                self.assertTrue(target.exists())
                self.assertEqual(Path(opened_urls[0]), target)
        finally:
            settings_window_module.QDesktopServices = original_desktop_services


if __name__ == "__main__":
    unittest.main()
