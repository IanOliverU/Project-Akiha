"""Tests for restoring persisted chat presentation metadata."""

from __future__ import annotations

import unittest

from project_akiha.app.main import _populate_chat_window
from project_akiha.core.memory import StoredMessage


class MainChatPopulationTest(unittest.TestCase):
    """Verify persisted subtitles remain optional presentation metadata."""

    def test_restores_subtitles_only_when_enabled(self) -> None:
        messages = (
            StoredMessage(
                id=1,
                conversation_id=7,
                role="assistant",
                content="こんにちは。",
                created_at="now",
                english_translation="Hello.",
            ),
        )
        enabled = _Surface()
        disabled = _Surface()

        _populate_chat_window(
            enabled,
            messages,
            "Akiha",
            show_english_subtitles=True,
        )
        _populate_chat_window(disabled, messages, "Akiha")

        self.assertEqual(enabled.messages, [("Akiha", "こんにちは。")])
        self.assertEqual(enabled.translations, ["Hello."])
        self.assertEqual(disabled.messages, [("Akiha", "こんにちは。")])
        self.assertEqual(disabled.translations, [])


class _Surface:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.translations: list[str] = []

    def append_message(self, speaker: str, content: str) -> None:
        self.messages.append((speaker, content))

    def append_assistant_translation(self, content: str) -> None:
        self.translations.append(content)


if __name__ == "__main__":
    unittest.main()
