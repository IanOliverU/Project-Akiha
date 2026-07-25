"""Tests for the chat window."""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from project_akiha.ui.chat_window import ChatWindow


class ChatWindowTest(unittest.TestCase):
    """Verify chat transcript rendering helpers."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_appends_idle_check_in_as_proactive_suggestion(self) -> None:
        window = ChatWindow()

        window.append_proactive_suggestion("Need a short break?", "idle_check_in")

        self.assertIn("Akiha check-in", window._history_view.toPlainText())
        self.assertIn("Need a short break?", window._history_view.toPlainText())

    def test_appends_scheduled_check_in_label(self) -> None:
        window = ChatWindow()

        window.append_proactive_suggestion("Still doing okay?", "scheduled_check_in")

        self.assertIn("Akiha scheduled check-in", window._history_view.toPlainText())

    def test_escapes_proactive_suggestion_content(self) -> None:
        window = ChatWindow()

        window.append_proactive_suggestion("<b>Take a break</b>", "unknown")

        self.assertIn("Akiha suggestion", window._history_view.toPlainText())
        self.assertIn("<b>Take a break</b>", window._history_view.toPlainText())
        self.assertNotIn("<b>Take a break</b>", window._history_view.toHtml())


if __name__ == "__main__":
    unittest.main()
