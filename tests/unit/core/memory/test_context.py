"""Tests for memory prompt context assembly."""

from __future__ import annotations

import unittest

from project_akiha.core.memory.context import (
    DefaultConversationSummaryContextAssembler,
    DefaultMemoryContextAssembler,
)
from project_akiha.core.memory.models import ConversationSummary, MemoryEntry


class DefaultMemoryContextAssemblerTest(unittest.TestCase):
    """Verify retrieved memory prompt rendering."""

    def test_assemble_returns_empty_string_without_memories(self) -> None:
        assembler = DefaultMemoryContextAssembler()

        self.assertEqual(assembler.assemble(()), "")

    def test_assemble_renders_memory_bullets(self) -> None:
        assembler = DefaultMemoryContextAssembler()

        context = assembler.assemble(
            (
                MemoryEntry(
                    id=1,
                    content="User prefers concise replies.",
                    source_conversation_id=None,
                    importance=3,
                    tags=("preference",),
                    created_at="now",
                    updated_at="now",
                    last_accessed_at=None,
                ),
            )
        )

        self.assertEqual(
            context,
            "Relevant memories about the user:\n- User prefers concise replies.",
        )


class DefaultConversationSummaryContextAssemblerTest(unittest.TestCase):
    """Verify closed-conversation summary prompt rendering."""

    def test_assemble_returns_empty_string_without_summaries(self) -> None:
        assembler = DefaultConversationSummaryContextAssembler()

        self.assertEqual(assembler.assemble(()), "")

    def test_assemble_renders_summary_bullets(self) -> None:
        assembler = DefaultConversationSummaryContextAssembler()

        context = assembler.assemble(
            (
                ConversationSummary(
                    id=1,
                    title="Previous chat",
                    summary="User discussed Phase 3 memory work.",
                    created_at="then",
                    updated_at="then",
                    closed_at="then",
                ),
            )
        )

        self.assertEqual(
            context,
            "Recent conversation summaries:\n- User discussed Phase 3 memory work.",
        )


if __name__ == "__main__":
    unittest.main()
