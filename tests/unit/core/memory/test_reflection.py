"""Tests for manual memory reflection jobs."""

from __future__ import annotations

import unittest

from project_akiha.core.memory import DefaultMemoryReflector
from project_akiha.core.memory.models import ConversationSummary, MemoryEntry


class DefaultMemoryReflectorTest(unittest.TestCase):
    """Verify reflection candidate generation."""

    def test_reflects_recent_summaries_into_candidates(self) -> None:
        reflector = DefaultMemoryReflector()

        candidates = reflector.reflect(
            memories=(),
            summaries=(_summary(1, "User discussed Project Akiha memory work."),),
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0].content,
            "Recent context: User discussed Project Akiha memory work.",
        )
        self.assertEqual(candidates[0].source_role, "user")
        self.assertEqual(candidates[0].tags, ("reflection", "conversation-summary"))

    def test_reflection_skips_existing_memory_content(self) -> None:
        reflector = DefaultMemoryReflector()

        candidates = reflector.reflect(
            memories=(
                _memory("Recent context: User discussed Project Akiha memory work."),
            ),
            summaries=(_summary(1, "User discussed Project Akiha memory work."),),
        )

        self.assertEqual(candidates, ())

    def test_reflection_respects_summary_limit(self) -> None:
        reflector = DefaultMemoryReflector(summary_limit=1)

        candidates = reflector.reflect(
            memories=(),
            summaries=(
                _summary(1, "First summary."),
                _summary(2, "Second summary."),
            ),
        )

        self.assertEqual(len(candidates), 1)
        self.assertIn("First summary.", candidates[0].content)

    def test_reflection_rejects_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            DefaultMemoryReflector(summary_limit=0)


def _summary(summary_id: int, summary: str) -> ConversationSummary:
    return ConversationSummary(
        id=summary_id,
        title="Closed chat",
        summary=summary,
        created_at="then",
        updated_at="then",
        closed_at="then",
    )


def _memory(content: str) -> MemoryEntry:
    return MemoryEntry(
        id=1,
        content=content,
        source_conversation_id=None,
        importance=3,
        tags=("reflection",),
        created_at="now",
        updated_at="now",
        last_accessed_at=None,
    )


if __name__ == "__main__":
    unittest.main()
