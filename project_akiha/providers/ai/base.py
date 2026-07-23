"""Framework-free AI provider contract."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

ChatRole = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A single chat message exchanged with the AI provider."""

    role: ChatRole
    content: str


class AIProvider(Protocol):
    """Generate assistant responses for chat history."""

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        """Return a complete assistant response for the given messages."""

    async def is_available(self) -> bool:
        """Return whether this provider is ready to answer."""
