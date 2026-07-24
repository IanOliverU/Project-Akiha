"""Tests for memory candidate normalization."""

from __future__ import annotations

import unittest

from project_akiha.core.memory.models import MemoryCandidate
from project_akiha.core.memory.normalization import DefaultMemoryNormalizer


class DefaultMemoryNormalizerTest(unittest.TestCase):
    """Verify deterministic memory cleanup."""

    def test_normalizes_content_tags_and_importance(self) -> None:
        normalizer = DefaultMemoryNormalizer()

        candidate = normalizer.normalize(
            MemoryCandidate(
                content="  user   prefers concise replies  ",
                source_role="user",
                importance=9,
                tags=("Preference", "style", "style", " "),
            )
        )

        self.assertEqual(candidate.content, "user prefers concise replies.")
        self.assertEqual(candidate.importance, 5)
        self.assertEqual(candidate.tags, ("preference", "style"))


if __name__ == "__main__":
    unittest.main()
