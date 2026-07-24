"""Memory candidate normalization."""

from __future__ import annotations

from typing import Protocol

from project_akiha.core.memory.models import MemoryCandidate


class MemoryNormalizer(Protocol):
    """Normalize accepted memory candidates before storage."""

    def normalize(self, candidate: MemoryCandidate) -> MemoryCandidate:
        """Return a cleaned candidate."""


class DefaultMemoryNormalizer:
    """Apply deterministic cleanup to memory candidates."""

    def normalize(self, candidate: MemoryCandidate) -> MemoryCandidate:
        """Return a candidate with normalized content and tags."""
        return MemoryCandidate(
            content=_normalize_content(candidate.content),
            source_role=candidate.source_role,
            confidence=candidate.confidence,
            importance=max(1, min(5, candidate.importance)),
            tags=_normalize_tags(candidate.tags),
        )


def _normalize_content(content: str) -> str:
    normalized = " ".join(content.split()).strip()
    if not normalized:
        return normalized
    if normalized[-1] not in ".!?":
        normalized = f"{normalized}."
    return normalized


def _normalize_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(tag.strip().lower() for tag in tags if tag.strip()))
