"""Embedding helpers for memory retrieval."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Create a numeric representation for memory search text."""

    def embed(self, text: str) -> tuple[float, ...]:
        """Return an embedding vector."""


class HashingEmbeddingProvider:
    """Deterministic local embedding provider for dependency-free vector search."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions <= 0:
            raise ValueError("embedding dimensions must be greater than zero.")
        self._dimensions = dimensions

    def embed(self, text: str) -> tuple[float, ...]:
        """Return a normalized signed hashing vector."""
        vector = [0.0] * self._dimensions
        for token in _tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return tuple(vector)

        return tuple(value / magnitude for value in vector)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Return cosine similarity for same-sized normalized vectors."""
    if not left or len(left) != len(right):
        return 0.0

    return sum(
        left_value * right_value
        for left_value, right_value in zip(left, right, strict=True)
    )


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9']+", text.casefold()))
