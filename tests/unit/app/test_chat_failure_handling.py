"""Tests for chat provider failure handling."""

from __future__ import annotations

import logging
import unittest

from project_akiha.app.main import _handle_chat_failure


class ChatFailureHandlingTest(unittest.TestCase):
    """Verify chat failures are logged and surfaced without raising."""

    def test_logs_failure_and_appends_visible_chat_error(self) -> None:
        chat_window = _RecordingChatWindow()
        logger = logging.getLogger("test_chat_failure_handling")

        with self.assertLogs(logger, level="ERROR") as captured:
            _handle_chat_failure("provider failed", chat_window, logger)

        self.assertIn(
            "AI provider response failed: provider failed",
            captured.output[0],
        )
        self.assertEqual(chat_window.errors, ["provider failed"])

    def test_blank_failure_message_uses_fallback_text(self) -> None:
        chat_window = _RecordingChatWindow()
        logger = logging.getLogger("test_blank_chat_failure")

        with self.assertLogs(logger, level="ERROR") as captured:
            _handle_chat_failure("   ", chat_window, logger)

        self.assertIn("Unknown chat provider failure.", captured.output[0])
        self.assertEqual(chat_window.errors, ["Unknown chat provider failure."])


class _RecordingChatWindow:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def append_error(self, content: str) -> None:
        self.errors.append(content)


if __name__ == "__main__":
    unittest.main()
