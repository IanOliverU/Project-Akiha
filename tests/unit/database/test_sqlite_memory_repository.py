"""Tests for SQLite durable memory persistence."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from project_akiha.database import SQLiteConversationRepository, SQLiteMemoryRepository


class SQLiteMemoryRepositoryTest(unittest.TestCase):
    """Verify durable memory storage and retrieval."""

    def test_saves_and_loads_recent_memories(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "akiha.sqlite3"
            repository = SQLiteMemoryRepository(database_path)

            asyncio.run(
                repository.save_memory(
                    "User prefers concise answers.",
                    importance=4,
                    tags=("Preference", "style", "style"),
                )
            )
            asyncio.run(repository.save_memory("User likes dark mode.", importance=3))

            memories = asyncio.run(repository.get_recent_memories(limit=10))

        self.assertEqual(
            [memory.content for memory in memories],
            ["User likes dark mode.", "User prefers concise answers."],
        )
        self.assertEqual(memories[1].tags, ("preference", "style"))

    def test_memory_can_reference_source_conversation(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "akiha.sqlite3"
            conversation_repository = SQLiteConversationRepository(database_path)
            memory_repository = SQLiteMemoryRepository(database_path)
            conversation = asyncio.run(
                conversation_repository.get_or_create_current_conversation()
            )

            memory = asyncio.run(
                memory_repository.save_memory(
                    "User is building Project Akiha.",
                    source_conversation_id=conversation.id,
                    importance=5,
                )
            )

        self.assertEqual(memory.source_conversation_id, conversation.id)

    def test_retrieve_relevant_memories_matches_content_or_tags(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteMemoryRepository(Path(directory) / "akiha.sqlite3")
            asyncio.run(
                repository.save_memory(
                    "User prefers concise answers.",
                    importance=3,
                    tags=("style",),
                )
            )
            asyncio.run(
                repository.save_memory(
                    "User likes dark mode.",
                    importance=5,
                    tags=("appearance",),
                )
            )

            dark_matches = asyncio.run(
                repository.retrieve_relevant_memories("dark", limit=5)
            )
            style_matches = asyncio.run(
                repository.retrieve_relevant_memories("style", limit=5)
            )

        self.assertEqual(
            [memory.content for memory in dark_matches], ["User likes dark mode."]
        )
        self.assertEqual(
            [memory.content for memory in style_matches],
            ["User prefers concise answers."],
        )

    def test_delete_memory_removes_it_from_retrieval(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteMemoryRepository(Path(directory) / "akiha.sqlite3")
            memory = asyncio.run(repository.save_memory("Forget this later."))

            asyncio.run(repository.delete_memory(memory.id))
            memories = asyncio.run(repository.get_recent_memories(limit=10))

        self.assertEqual(memories, ())

    def test_clear_memories_removes_all_memories(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteMemoryRepository(Path(directory) / "akiha.sqlite3")
            asyncio.run(repository.save_memory("First memory."))
            asyncio.run(repository.save_memory("Second memory."))

            asyncio.run(repository.clear_memories())
            memories = asyncio.run(repository.get_recent_memories(limit=10))

        self.assertEqual(memories, ())

    def test_validates_memory_input(self) -> None:
        with TemporaryDirectory() as directory:
            repository = SQLiteMemoryRepository(Path(directory) / "akiha.sqlite3")

            with self.assertRaises(ValueError):
                asyncio.run(repository.save_memory("   "))
            with self.assertRaises(ValueError):
                asyncio.run(repository.save_memory("Too important.", importance=6))
            with self.assertRaises(ValueError):
                asyncio.run(repository.get_recent_memories(limit=0))


if __name__ == "__main__":
    unittest.main()
