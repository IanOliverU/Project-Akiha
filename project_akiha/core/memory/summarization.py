"""Conversation summary generation for closed chats."""

from __future__ import annotations

from collections.abc import Awaitable, Sequence
from typing import Protocol

from project_akiha.core.memory.models import MessageRole


class SummarySourceMessage(Protocol):
    """Minimal message shape needed for conversation summarization."""

    role: MessageRole
    content: str


class ConversationSummarizer(Protocol):
    """Create a compact digest of a transcript."""

    def summarize(
        self,
        messages: Sequence[SummarySourceMessage],
    ) -> str | Awaitable[str]:
        """Return a compact summary, or an empty string when there is nothing useful."""


class HeuristicConversationSummarizer:
    """Deterministic first-pass summarizer for closed conversations."""

    def __init__(self, max_user_points: int = 3, max_point_length: int = 90) -> None:
        self._max_user_points = max_user_points
        self._max_point_length = max_point_length

    def summarize(self, messages: Sequence[SummarySourceMessage]) -> str:
        """Summarize the visible user/assistant exchange without external AI."""
        visible_messages = [
            message for message in messages if message.role in {"user", "assistant"}
        ]
        if not visible_messages:
            return ""

        user_messages = [
            message.content.strip()
            for message in visible_messages
            if message.role == "user"
        ]
        assistant_count = len(visible_messages) - len(user_messages)
        if not user_messages:
            return f"Conversation had {len(visible_messages)} visible messages."

        points = [
            _clip(message, self._max_point_length)
            for message in user_messages[: self._max_user_points]
            if message
        ]
        if not points:
            return ""

        plural = "message" if len(visible_messages) == 1 else "messages"
        summary = (
            f"Conversation had {len(visible_messages)} visible {plural} "
            f"({len(user_messages)} user, {assistant_count} assistant). "
            f"User discussed: {'; '.join(points)}."
        )
        return summary


def _clip(content: str, max_length: int) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_length:
        return normalized

    return f"{normalized[: max_length - 1].rstrip()}..."
