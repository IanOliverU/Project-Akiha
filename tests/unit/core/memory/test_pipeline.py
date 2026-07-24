"""Tests for memory pipeline orchestration."""

from __future__ import annotations

import unittest

from project_akiha.core.memory.models import MemoryEntry
from project_akiha.core.memory.pipeline import MemoryPipeline
from project_akiha.providers.ai import ChatMessage


class RecordingMemoryRepository:
    """Test memory repository that records saved memories."""

    def __init__(self) -> None:
        self.saved_memories: list[tuple[str, int | None, int, tuple[str, ...]]] = []
        self.existing_memories: tuple[MemoryEntry, ...] = ()

    async def save_memory(
        self,
        content: str,
        source_conversation_id: int | None = None,
        importance: int = 3,
        tags: tuple[str, ...] = (),
    ) -> MemoryEntry:
        """Record a saved memory."""
        self.saved_memories.append(
            (content, source_conversation_id, importance, tuple(tags))
        )
        return MemoryEntry(
            id=len(self.saved_memories),
            content=content,
            source_conversation_id=source_conversation_id,
            importance=importance,
            tags=tuple(tags),
            created_at="now",
            updated_at="now",
            last_accessed_at=None,
        )

    async def get_recent_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        """Return configured memories."""
        del limit
        return self.existing_memories

    async def retrieve_relevant_memories(
        self,
        query: str,
        limit: int,
    ) -> tuple[MemoryEntry, ...]:
        """Return no relevant memories for test use."""
        del query, limit
        return ()

    async def delete_memory(self, memory_id: int) -> None:
        """Ignore deletion for test use."""
        del memory_id


class MemoryPipelineTest(unittest.IsolatedAsyncioTestCase):
    """Verify memory pipeline stages work together."""

    async def test_process_messages_saves_accepted_candidate(self) -> None:
        repository = RecordingMemoryRepository()
        pipeline = MemoryPipeline(repository)

        saved = await pipeline.process_messages(
            (ChatMessage(role="user", content="Remember that I use Krita."),),
            source_conversation_id=7,
        )

        self.assertEqual(len(saved), 1)
        self.assertEqual(
            repository.saved_memories,
            [("I use Krita.", 7, 4, ("explicit",))],
        )

    async def test_process_messages_skips_duplicate_candidate(self) -> None:
        repository = RecordingMemoryRepository()
        repository.existing_memories = (
            MemoryEntry(
                id=1,
                content="I use Krita.",
                source_conversation_id=7,
                importance=4,
                tags=("explicit",),
                created_at="now",
                updated_at="now",
                last_accessed_at=None,
            ),
        )
        pipeline = MemoryPipeline(repository)

        saved = await pipeline.process_messages(
            (ChatMessage(role="user", content="Remember that I use Krita."),),
            source_conversation_id=7,
        )

        self.assertEqual(saved, ())
        self.assertEqual(repository.saved_memories, [])


if __name__ == "__main__":
    unittest.main()
