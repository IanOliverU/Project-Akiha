"""Memory context assembly for chat prompts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from project_akiha.core.memory.models import ConversationSummary, MemoryEntry


class MemoryContextAssembler(Protocol):
    """Render retrieved memories into provider prompt context."""

    def assemble(self, memories: Sequence[MemoryEntry]) -> str:
        """Return prompt text for relevant memories."""


class ConversationSummaryContextAssembler(Protocol):
    """Render conversation summaries into provider prompt context."""

    def assemble(self, summaries: Sequence[ConversationSummary]) -> str:
        """Return prompt text for recent conversation summaries."""


class DefaultMemoryContextAssembler:
    """Render memories as a compact system prompt section."""

    def assemble(self, memories: Sequence[MemoryEntry]) -> str:
        """Return a hidden context block for provider calls."""
        if not memories:
            return ""

        lines = ["Relevant memories about the user:"]
        for memory in memories:
            lines.append(f"- {memory.content}")

        return "\n".join(lines)


class DefaultConversationSummaryContextAssembler:
    """Render closed-conversation summaries as compact prompt context."""

    def assemble(self, summaries: Sequence[ConversationSummary]) -> str:
        """Return a hidden context block for provider calls."""
        if not summaries:
            return ""

        lines = ["Recent conversation summaries:"]
        for summary in summaries:
            lines.append(f"- {summary.summary}")

        return "\n".join(lines)
