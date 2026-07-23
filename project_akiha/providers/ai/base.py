"""Framework-free AI provider contract."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from project_akiha.core.memory.models import MessageRole

ChatRole = MessageRole


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single chat message exchanged with the AI provider."""

    role: ChatRole
    content: str


class AIProvider(Protocol):
    """Generate assistant responses for chat history."""

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        """Return a complete assistant response for the given messages."""

    def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        """Yield assistant response text as it becomes available."""

    async def is_available(self) -> bool:
        """Return whether this provider is ready to answer."""
