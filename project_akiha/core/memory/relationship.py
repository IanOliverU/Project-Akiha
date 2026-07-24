"""Relationship and emotional context modeling from memories."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from project_akiha.core.memory.models import MemoryEntry


@dataclass(frozen=True, slots=True)
class RelationshipProfile:
    """A structured view of remembered user context."""

    identity: tuple[str, ...] = ()
    preferences: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    boundaries: tuple[str, ...] = ()
    emotional_cues: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        """Return whether the profile has no relationship context."""
        return not any(
            (
                self.identity,
                self.preferences,
                self.goals,
                self.tools,
                self.boundaries,
                self.emotional_cues,
            )
        )


class RelationshipMemoryModeler(Protocol):
    """Build relationship context from remembered facts."""

    def model(self, memories: Sequence[MemoryEntry]) -> RelationshipProfile:
        """Return a structured relationship profile."""


class DefaultRelationshipMemoryModeler:
    """Classify remembered facts into companion relationship context."""

    def __init__(self, per_category_limit: int = 3) -> None:
        if per_category_limit <= 0:
            raise ValueError("relationship category limit must be greater than zero.")
        self._per_category_limit = per_category_limit

    def model(self, memories: Sequence[MemoryEntry]) -> RelationshipProfile:
        """Return deterministic relationship context from memory tags and text."""
        identity: list[str] = []
        preferences: list[str] = []
        goals: list[str] = []
        tools: list[str] = []
        boundaries: list[str] = []
        emotional_cues: list[str] = []

        for memory in memories:
            content = memory.content.strip()
            if not content:
                continue

            tags = set(memory.tags)
            normalized = content.casefold()
            _append_if(identity, content, tags, normalized, _IDENTITY_MARKERS)
            _append_if(preferences, content, tags, normalized, _PREFERENCE_MARKERS)
            _append_if(goals, content, tags, normalized, _GOAL_MARKERS)
            _append_if(tools, content, tags, normalized, _TOOL_MARKERS)
            _append_if(boundaries, content, tags, normalized, _BOUNDARY_MARKERS)
            _append_if(
                emotional_cues,
                content,
                tags,
                normalized,
                _EMOTIONAL_MARKERS,
            )

        return RelationshipProfile(
            identity=_limited_unique(identity, self._per_category_limit),
            preferences=_limited_unique(preferences, self._per_category_limit),
            goals=_limited_unique(goals, self._per_category_limit),
            tools=_limited_unique(tools, self._per_category_limit),
            boundaries=_limited_unique(boundaries, self._per_category_limit),
            emotional_cues=_limited_unique(emotional_cues, self._per_category_limit),
        )


_IDENTITY_MARKERS = (("identity",), ("name is", "user's name"))
_PREFERENCE_MARKERS = (("preference",), ("prefers", "likes"))
_GOAL_MARKERS = (
    ("goal", "project"),
    ("building", "working on", "wants", "needs to", "goal"),
)
_TOOL_MARKERS = (("tool",), ("uses", "works with"))
_BOUNDARY_MARKERS = (
    ("boundary", "constraint"),
    ("avoid", "does not", "cannot", "prefers not", "constraint"),
)
_EMOTIONAL_MARKERS = (
    ("emotion", "emotional", "mood"),
    ("anxious", "excited", "frustrated", "worried", "overwhelmed", "happy"),
)


def _append_if(
    target: list[str],
    content: str,
    tags: set[str],
    normalized_content: str,
    markers: tuple[tuple[str, ...], tuple[str, ...]],
) -> None:
    tag_markers, text_markers = markers
    if tags.intersection(tag_markers) or any(
        marker in normalized_content for marker in text_markers
    ):
        target.append(content)


def _limited_unique(values: list[str], limit: int) -> tuple[str, ...]:
    unique_values = tuple(dict.fromkeys(values))
    return unique_values[:limit]
