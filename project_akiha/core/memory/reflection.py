"""Manual reflection jobs for memory learning."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from project_akiha.core.memory.models import (
    ConversationSummary,
    MemoryCandidate,
    MemoryEntry,
)


class MemoryReflector(Protocol):
    """Generate memory candidates from existing long-term context."""

    def reflect(
        self,
        memories: Sequence[MemoryEntry],
        summaries: Sequence[ConversationSummary],
    ) -> tuple[MemoryCandidate, ...]:
        """Return candidate memories discovered during reflection."""


class DefaultMemoryReflector:
    """Conservative deterministic reflector for user-triggered learning jobs."""

    def __init__(self, summary_limit: int = 5) -> None:
        if summary_limit <= 0:
            raise ValueError("reflection summary limit must be greater than zero.")
        self._summary_limit = summary_limit

    def reflect(
        self,
        memories: Sequence[MemoryEntry],
        summaries: Sequence[ConversationSummary],
    ) -> tuple[MemoryCandidate, ...]:
        """Turn recent conversation summaries into approval-gated candidates."""
        existing = {_normalize(memory.content) for memory in memories}
        candidates: list[MemoryCandidate] = []
        for summary in summaries[: self._summary_limit]:
            content = _candidate_content(summary.summary)
            if not content or _normalize(content) in existing:
                continue

            candidates.append(
                MemoryCandidate(
                    content=content,
                    source_role="user",
                    confidence=0.72,
                    importance=2,
                    tags=("reflection", "conversation-summary"),
                )
            )

        return tuple(candidates)


def _candidate_content(summary: str) -> str:
    normalized = " ".join(summary.split()).strip()
    if not normalized:
        return ""

    return f"Recent context: {normalized}"


def _normalize(content: str) -> str:
    return " ".join(content.casefold().strip().rstrip(" .!?").split())
