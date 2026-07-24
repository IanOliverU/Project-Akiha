"""Memory candidate validation policy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from project_akiha.core.memory.models import MemoryCandidate, MemoryEntry


class MemoryPolicy(Protocol):
    """Decide whether a memory candidate should be stored."""

    def accepts(
        self,
        candidate: MemoryCandidate,
        existing_memories: Sequence[MemoryEntry] = (),
    ) -> bool:
        """Return whether a candidate is acceptable."""


class DefaultMemoryPolicy:
    """Conservative deterministic policy for the first memory pass."""

    def __init__(self, minimum_confidence: float = 0.7) -> None:
        self._minimum_confidence = minimum_confidence

    def accepts(
        self,
        candidate: MemoryCandidate,
        existing_memories: Sequence[MemoryEntry] = (),
    ) -> bool:
        """Return whether a candidate is specific enough to persist."""
        normalized_content = _normalize_for_comparison(candidate.content)
        if not normalized_content:
            return False
        if candidate.source_role != "user":
            return False
        if candidate.confidence < self._minimum_confidence:
            return False
        if len(normalized_content) < 8:
            return False

        existing_content = {
            _normalize_for_comparison(memory.content) for memory in existing_memories
        }
        return normalized_content not in existing_content


def _normalize_for_comparison(content: str) -> str:
    return " ".join(content.strip().lower().rstrip(" .!?").split())
