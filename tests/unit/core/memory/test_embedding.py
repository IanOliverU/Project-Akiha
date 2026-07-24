"""Tests for memory embedding helpers."""

from __future__ import annotations

import unittest

from project_akiha.core.memory.embedding import (
    HashingEmbeddingProvider,
    cosine_similarity,
)


class HashingEmbeddingProviderTest(unittest.TestCase):
    """Verify deterministic local embeddings."""

    def test_embed_returns_normalized_deterministic_vector(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=16)

        first = provider.embed("User uses Krita.")
        second = provider.embed("User uses Krita.")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 16)
        self.assertAlmostEqual(cosine_similarity(first, first), 1.0)

    def test_embed_rejects_invalid_dimensions(self) -> None:
        with self.assertRaises(ValueError):
            HashingEmbeddingProvider(dimensions=0)

    def test_empty_text_returns_zero_vector(self) -> None:
        provider = HashingEmbeddingProvider(dimensions=4)

        self.assertEqual(provider.embed("   "), (0.0, 0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
