"""Tests for the settings window."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QApplication, QGroupBox

import project_akiha.ui.settings_window as settings_window_module
from project_akiha.config import AIConfig, AppConfig, PrivacyConfig
from project_akiha.core.actions import ApprovedDirectory, InstalledApplication
from project_akiha.services.ai_provider_discovery import (
    AIProviderDiscoveryResult,
)
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

    def test_uniform_theme_and_sections_are_applied(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

        section_titles = {
            section.title()
            for section in window.findChildren(QGroupBox)
            if section.objectName() == "settingsSection"
        }
        self.assertEqual(window.objectName(), "akihaSettingsWindow")
        self.assertEqual(window._tabs.count(), 6)
        self.assertEqual(window._save_button.objectName(), "primaryButton")
        self.assertIn(AKIHA_PALETTE.window, window.styleSheet())
        self.assertIn(AKIHA_PALETTE.primary, window.styleSheet())
        self.assertTrue(
            {
                "Window",
                "Appearance",
                "Provider",
                "Identity",
                "Memory",
                "Awareness",
                "Proactive behavior",
                "Permission controls",
                "Approved directories",
                "Allowlisted applications",
                "Listening",
                "Speaking",
                "Subtitles",
                "Diagnostics",
            }.issubset(section_titles)
        )

    def test_assistant_permission_controls_refresh_and_emit_actions(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            directory_requests: list[tuple[str, bool, bool]] = []
            application_requests: list[str] = []
            window.assistant_directory_approval_requested.connect(
                lambda root, search, open_files: directory_requests.append(
                    (root, search, open_files)
                )
            )
            window.assistant_application_grant_requested.connect(
                application_requests.append
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
                (),
            )

            window._assistant_directory_list.setCurrentRow(0)
            window._assistant_directory_open_input.setChecked(True)
            window._apply_assistant_directory()
            window._assistant_application_list.setCurrentRow(0)
            window._enable_assistant_application()

        self.assertEqual(
            directory_requests,
            [(str(Path(directory).resolve()), True, True)],
        )
        self.assertEqual(application_requests, ["chrome"])
        self.assertIn(
            "Google Chrome", window._assistant_application_list.item(0).text()
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
            window._voice_output_base_url_input.setText("http://localhost:50021")
            window._voice_output_voice_id_input.setText("14")
            window._voice_output_device_input.setCurrentText("Desktop speakers")
            window._voice_output_engine_auto_start_input.setChecked(True)
            window._voice_output_engine_path_input.setText("C:/VOICEVOX Engine/run.exe")
            window._voice_output_engine_stop_on_exit_input.setChecked(False)
            window._voice_volume_input.setValue(75)
            window._voice_speaking_rate_input.setValue(1.2)
            window._voice_capture_timeout_input.setValue(12)
            window._voice_request_timeout_input.setValue(10)

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
        self.assertEqual(voice.output_provider, "voicevox")
        self.assertEqual(voice.output_base_url, "http://localhost:50021")
        self.assertEqual(voice.output_voice_id, "14")
        self.assertEqual(voice.output_device, "Desktop speakers")
        self.assertTrue(voice.output_engine_auto_start)
        self.assertEqual(
            voice.output_engine_path,
            "C:/VOICEVOX Engine/run.exe",
        )
        self.assertFalse(voice.output_engine_stop_on_exit)
        self.assertEqual(voice.volume_percent, 75)
        self.assertEqual(voice.speaking_rate, 1.2)
        self.assertEqual(voice.capture_timeout_seconds, 12)
        self.assertEqual(voice.request_timeout_seconds, 10)
        self.assertEqual(emitted[0].privacy.notice_version_acknowledged, 1)

    def test_voice_controls_follow_master_switch(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            self.assertFalse(window._automatic_speech_enabled_input.isEnabled())
            self.assertFalse(window._proactive_speech_enabled_input.isEnabled())
            self.assertFalse(window._english_subtitles_enabled_input.isEnabled())
            self.assertFalse(window._export_english_subtitles_enabled_input.isEnabled())
            self.assertFalse(window._live_transcription_enabled_input.isEnabled())
            self.assertFalse(window._voice_output_engine_auto_start_input.isEnabled())
            window._voice_enabled_input.setChecked(True)

        self.assertTrue(window._automatic_speech_enabled_input.isEnabled())
        self.assertTrue(window._proactive_speech_enabled_input.isEnabled())
        self.assertTrue(window._english_subtitles_enabled_input.isEnabled())
        self.assertTrue(window._export_english_subtitles_enabled_input.isEnabled())
        self.assertTrue(window._live_transcription_enabled_input.isEnabled())
        self.assertTrue(window._voice_output_base_url_input.isEnabled())
        self.assertTrue(window._voice_output_engine_auto_start_input.isEnabled())
        self.assertFalse(window._voice_output_engine_path_input.isEnabled())
        window._voice_output_engine_auto_start_input.setChecked(True)
        self.assertTrue(window._voice_output_engine_path_input.isEnabled())

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
                "VOICEVOX is not running.",
            )
            window.set_voice_diagnostic_status("Needs attention.", True)
            window.set_voice_test_active("microphone", True)

        self.assertEqual(requested, ["health", "microphone", "output"])
        self.assertIn("Whisper ready.", window._voice_input_health.text())
        self.assertIn("VOICEVOX is not running.", window._voice_output_health.text())
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
