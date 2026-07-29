"""Tests for tray presence helpers."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from project_akiha.ui.tray import AkihaTrayIcon


class AkihaTrayIconTest(unittest.TestCase):
    """Verify tray tooltip presence behavior."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def tearDown(self) -> None:
        if hasattr(self, "_tray_icon"):
            self._tray_icon.hide()
        for name in ("_pet_window", "_chat_window", "_settings_window"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.close()

    def test_sets_presence_text_in_tooltip(self) -> None:
        self._tray_icon = self._make_tray_icon()

        self._tray_icon.set_presence_text("Akiha is checking in.")

        self.assertEqual(
            self._tray_icon.toolTip(),
            "Project Akiha\nAkiha is checking in.",
        )

    def test_blank_presence_text_uses_fallback(self) -> None:
        self._tray_icon = self._make_tray_icon()

        self._tray_icon.set_presence_text("   ")

        self.assertEqual(
            self._tray_icon.toolTip(),
            "Project Akiha\nAkiha is nearby.",
        )

    def _make_tray_icon(self) -> AkihaTrayIcon:
        self._pet_window = QWidget()
        self._chat_window = QWidget()
        self._settings_window = QWidget()
        return AkihaTrayIcon(
            pet_window=self._pet_window,
            chat_window=self._chat_window,
            settings_window=self._settings_window,
        )


if __name__ == "__main__":
    unittest.main()
