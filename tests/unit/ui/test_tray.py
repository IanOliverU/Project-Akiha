"""Tests for tray presence helpers."""

from __future__ import annotations

import os
import sys
import unittest
from collections.abc import Callable

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

    def test_menu_show_and_hide_actions_control_pet_window(self) -> None:
        self._tray_icon = self._make_tray_icon()

        _trigger_action(self._tray_icon, "Show")
        self.assertTrue(self._pet_window.isVisible())

        _trigger_action(self._tray_icon, "Hide")
        self.assertFalse(self._pet_window.isVisible())

    def test_menu_chat_and_settings_actions_open_windows(self) -> None:
        self._tray_icon = self._make_tray_icon()

        _trigger_action(self._tray_icon, "Chat")
        _trigger_action(self._tray_icon, "Settings")

        self.assertTrue(self._chat_window.isVisible())
        self.assertTrue(self._settings_window.isVisible())

    def test_menu_behavior_history_action_emits_signal(self) -> None:
        self._tray_icon = self._make_tray_icon()
        emitted_count = 0

        def record_signal() -> None:
            nonlocal emitted_count
            emitted_count += 1

        self._tray_icon.behavior_history_requested.connect(record_signal)

        _trigger_action(self._tray_icon, "Behavior history")

        self.assertEqual(emitted_count, 1)

    def test_menu_care_action_emits_signal(self) -> None:
        self._tray_icon = self._make_tray_icon()
        emitted_count = 0

        def record_signal() -> None:
            nonlocal emitted_count
            emitted_count += 1

        self._tray_icon.pet_care_requested.connect(record_signal)

        _trigger_action(self._tray_icon, "Care")

        self.assertEqual(emitted_count, 1)

    def test_menu_quit_action_calls_quit_callback(self) -> None:
        quit_count = 0

        def record_quit() -> None:
            nonlocal quit_count
            quit_count += 1

        self._tray_icon = self._make_tray_icon(quit_callback=record_quit)

        _trigger_action(self._tray_icon, "Quit")

        self.assertEqual(quit_count, 1)

    def _make_tray_icon(
        self,
        quit_callback: Callable[[], None] | None = None,
    ) -> AkihaTrayIcon:
        self._pet_window = QWidget()
        self._chat_window = QWidget()
        self._settings_window = QWidget()
        return AkihaTrayIcon(
            pet_window=self._pet_window,
            chat_window=self._chat_window,
            settings_window=self._settings_window,
            quit_callback=quit_callback,
        )


def _trigger_action(tray_icon: AkihaTrayIcon, text: str) -> None:
    menu = tray_icon.contextMenu()
    assert menu is not None
    for action in menu.actions():
        if action.text() == text:
            action.trigger()
            return

    raise AssertionError(f"Tray action was not found: {text}")


if __name__ == "__main__":
    unittest.main()
