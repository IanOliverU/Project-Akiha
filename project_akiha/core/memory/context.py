"""Memory context assembly for chat prompts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from project_akiha.core.memory.models import ConversationSummary, MemoryEntry
from project_akiha.core.memory.relationship import RelationshipProfile


class MemoryContextAssembler(Protocol):
    """Render retrieved memories into provider prompt context."""

    def assemble(self, memories: Sequence[MemoryEntry]) -> str:
        """Return prompt text for relevant memories."""


class ConversationSummaryContextAssembler(Protocol):
    """Render conversation summaries into provider prompt context."""

    def assemble(self, summaries: Sequence[ConversationSummary]) -> str:
        """Return prompt text for recent conversation summaries."""


class RelationshipContextAssembler(Protocol):
    """Render relationship context into provider prompt context."""

    def assemble(self, profile: RelationshipProfile) -> str:
        """Return prompt text for relationship context."""


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


class DefaultRelationshipContextAssembler:
    """Render a structured relationship profile as compact prompt context."""

    def assemble(self, profile: RelationshipProfile) -> str:
        """Return a hidden context block for provider calls."""
        if profile.is_empty():
            return ""

        lines = ["Relationship context about the user:"]
        _append_profile_line(lines, "Identity", profile.identity)
        _append_profile_line(lines, "Preferences", profile.preferences)
        _append_profile_line(lines, "Goals", profile.goals)
        _append_profile_line(lines, "Tools", profile.tools)
        _append_profile_line(lines, "Boundaries", profile.boundaries)
        _append_profile_line(lines, "Emotional cues", profile.emotional_cues)
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


def _append_profile_line(
    lines: list[str],
    label: str,
    values: tuple[str, ...],
) -> None:
    if values:
        lines.append(f"- {label}: {'; '.join(values)}")
