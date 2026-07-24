"""Tests for memory validation policy."""

from __future__ import annotations

import unittest

from project_akiha.core.memory.models import MemoryCandidate, MemoryEntry
from project_akiha.core.memory.validation import DefaultMemoryPolicy


class DefaultMemoryPolicyTest(unittest.TestCase):
    """Verify conservative candidate acceptance."""

    def test_accepts_specific_user_candidate(self) -> None:
        policy = DefaultMemoryPolicy()

        self.assertTrue(
            policy.accepts(
                MemoryCandidate(
                    content="User prefers concise replies.",
                    source_role="user",
                    confidence=0.8,
                )
            )
        )

    def test_rejects_low_confidence_candidate(self) -> None:
        policy = DefaultMemoryPolicy()

        self.assertFalse(
            policy.accepts(
                MemoryCandidate(
                    content="User prefers concise replies.",
                    source_role="user",
                    confidence=0.2,
                )
            )
        )

    def test_rejects_assistant_candidate(self) -> None:
        policy = DefaultMemoryPolicy()

        self.assertFalse(
            policy.accepts(
                MemoryCandidate(
                    content="Assistant invented a preference.",
                    source_role="assistant",
                    confidence=0.9,
                )
            )
        )

    def test_rejects_duplicate_memory(self) -> None:
        policy = DefaultMemoryPolicy()
        existing_memory = MemoryEntry(
            id=1,
            content="User prefers concise replies.",
            source_conversation_id=None,
            importance=3,
            tags=(),
            created_at="now",
            updated_at="now",
            last_accessed_at=None,
        )

        self.assertFalse(
            policy.accepts(
                MemoryCandidate(
                    content="user prefers concise replies",
                    source_role="user",
                    confidence=0.9,
                ),
                existing_memories=(existing_memory,),
            )
        )


if __name__ == "__main__":
    unittest.main()
