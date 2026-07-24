"""Tests for relationship memory modeling."""

from __future__ import annotations

import unittest

from project_akiha.core.memory import DefaultRelationshipMemoryModeler
from project_akiha.core.memory.models import MemoryEntry


class DefaultRelationshipMemoryModelerTest(unittest.TestCase):
    """Verify deterministic relationship profile generation."""

    def test_model_groups_memories_by_tags_and_content(self) -> None:
        modeler = DefaultRelationshipMemoryModeler()

        profile = modeler.model(
            (
                _memory("User's name is Yuki.", tags=("identity",)),
                _memory("User prefers concise replies.", tags=("preference",)),
                _memory("User is building Project Akiha.", tags=("project",)),
                _memory("User uses Krita.", tags=("tool",)),
                _memory("User cannot work with loud notifications."),
                _memory("User feels overwhelmed by large tasks.", tags=("emotion",)),
            )
        )

        self.assertEqual(profile.identity, ("User's name is Yuki.",))
        self.assertEqual(profile.preferences, ("User prefers concise replies.",))
        self.assertEqual(profile.goals, ("User is building Project Akiha.",))
        self.assertEqual(profile.tools, ("User uses Krita.",))
        self.assertEqual(
            profile.boundaries, ("User cannot work with loud notifications.",)
        )
        self.assertEqual(
            profile.emotional_cues,
            ("User feels overwhelmed by large tasks.",),
        )

    def test_model_limits_and_deduplicates_category_values(self) -> None:
        modeler = DefaultRelationshipMemoryModeler(per_category_limit=2)

        profile = modeler.model(
            (
                _memory("User prefers concise replies.", tags=("preference",)),
                _memory("User prefers concise replies.", tags=("preference",)),
                _memory("User prefers dark mode.", tags=("preference",)),
                _memory("User prefers quiet notifications.", tags=("preference",)),
            )
        )

        self.assertEqual(
            profile.preferences,
            ("User prefers concise replies.", "User prefers dark mode."),
        )

    def test_model_rejects_invalid_limit(self) -> None:
        with self.assertRaises(ValueError):
            DefaultRelationshipMemoryModeler(per_category_limit=0)


def _memory(content: str, tags: tuple[str, ...] = ()) -> MemoryEntry:
    return MemoryEntry(
        id=1,
        content=content,
        source_conversation_id=None,
        importance=3,
        tags=tags,
        created_at="now",
        updated_at="now",
        last_accessed_at=None,
    )


if __name__ == "__main__":
    unittest.main()
