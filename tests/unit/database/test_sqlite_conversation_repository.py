"""Tests for SQLite conversation transcript persistence."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.database import SQLiteConversationRepository


class SQLiteConversationRepositoryTest(unittest.TestCase):
    """Verify conversation and message persistence."""

    def test_get_or_create_current_conversation_reuses_open_conversation(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteConversationRepository(Path(directory) / "akiha.sqlite3")

            first = asyncio.run(repository.get_or_create_current_conversation())
            second = asyncio.run(repository.get_or_create_current_conversation())

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.title, "Current chat")
        self.assertIsNone(first.closed_at)

    def test_saves_and_loads_recent_messages_in_chronological_order(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteConversationRepository(Path(directory) / "akiha.sqlite3")
            conversation = asyncio.run(repository.get_or_create_current_conversation())

            asyncio.run(repository.save_message(conversation.id, "user", "one"))
            asyncio.run(repository.save_message(conversation.id, "assistant", "two"))
            asyncio.run(repository.save_message(conversation.id, "user", "three"))

            messages = asyncio.run(
                repository.get_recent_messages(conversation.id, limit=2)
            )

        self.assertEqual([message.content for message in messages], ["two", "three"])
        self.assertEqual([message.role for message in messages], ["assistant", "user"])

    def test_rejects_empty_message_content(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteConversationRepository(Path(directory) / "akiha.sqlite3")
            conversation = asyncio.run(repository.get_or_create_current_conversation())

            with self.assertRaises(ValueError):
                asyncio.run(repository.save_message(conversation.id, "user", "   "))


if __name__ == "__main__":
    unittest.main()
