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

from project_akiha.config import AppConfig
from project_akiha.ui.settings_window import SettingsWindow


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
            window._idle_after_input.setValue(120)
            window._away_after_input.setValue(240)
            window._notification_cooldown_input.setValue(600)
            window._allow_notifications_while_away_input.setChecked(True)
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
        self.assertTrue(emitted[0].behavior.quiet_hours_enabled)
        self.assertEqual(emitted[0].behavior.quiet_hours_start, "21:30")
        self.assertEqual(emitted[0].behavior.quiet_hours_end, "08:15")


if __name__ == "__main__":
    unittest.main()
