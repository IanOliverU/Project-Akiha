"""Tests for the settings window."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTime
from PySide6.QtWidgets import QApplication

import project_akiha.ui.settings_window as settings_window_module
from project_akiha.config import AppConfig
from project_akiha.ui.settings_window import SettingsWindow


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

    def test_saves_voice_controls(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))
            emitted: list[AppConfig] = []
            window.settings_saved.connect(emitted.append)

            window._voice_enabled_input.setChecked(True)
            window._automatic_speech_enabled_input.setChecked(True)
            window._voice_input_model_input.setText("medium")
            window._voice_input_language_input.setCurrentText("ja")
            window._voice_input_device_input.setCurrentText("USB microphone")
            window._voice_output_base_url_input.setText("http://localhost:50021")
            window._voice_output_voice_id_input.setText("14")
            window._voice_output_device_input.setCurrentText("Desktop speakers")
            window._voice_volume_input.setValue(75)
            window._voice_speaking_rate_input.setValue(1.2)
            window._voice_capture_timeout_input.setValue(12)
            window._voice_request_timeout_input.setValue(10)

            window._save()

        voice = emitted[0].voice
        self.assertTrue(voice.enabled)
        self.assertTrue(voice.automatic_speech_enabled)
        self.assertEqual(voice.input_provider, "faster-whisper")
        self.assertEqual(voice.input_model, "medium")
        self.assertEqual(voice.input_language, "ja")
        self.assertEqual(voice.input_device, "USB microphone")
        self.assertEqual(voice.output_provider, "voicevox")
        self.assertEqual(voice.output_base_url, "http://localhost:50021")
        self.assertEqual(voice.output_voice_id, "14")
        self.assertEqual(voice.output_device, "Desktop speakers")
        self.assertEqual(voice.volume_percent, 75)
        self.assertEqual(voice.speaking_rate, 1.2)
        self.assertEqual(voice.capture_timeout_seconds, 12)
        self.assertEqual(voice.request_timeout_seconds, 10)

    def test_voice_controls_follow_master_switch(self) -> None:
        with TemporaryDirectory() as directory:
            window = SettingsWindow(AppConfig(), log_dir=Path(directory))

            self.assertFalse(window._automatic_speech_enabled_input.isEnabled())
            window._voice_enabled_input.setChecked(True)

        self.assertTrue(window._automatic_speech_enabled_input.isEnabled())
        self.assertTrue(window._voice_output_base_url_input.isEnabled())

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
