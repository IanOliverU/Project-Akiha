"""Repository protocols for conversation persistence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from project_akiha.core.memory.models import (
    Conversation,
    MemoryEntry,
    MessageRole,
    StoredMessage,
)


class ConversationRepository(Protocol):
    """Persist and load raw conversation transcripts."""

    async def create_conversation(self, title: str = "Current chat") -> Conversation:
        """Create a new open conversation."""

    async def get_or_create_current_conversation(self) -> Conversation:
        """Return the open conversation used for the current chat session."""

    async def close_conversation(self, conversation_id: int) -> None:
        """Mark a conversation as closed."""

    async def clear_conversation_messages(self, conversation_id: int) -> None:
        """Delete all messages in a conversation."""

    async def save_message(
        self,
        conversation_id: int,
        role: MessageRole,
        content: str,
    ) -> StoredMessage:
        """Persist one transcript message."""

    async def get_recent_messages(
        self,
        conversation_id: int,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        """Return recent transcript messages in chronological order."""

    async def get_messages(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Return all transcript messages in chronological order."""


class MemoryRepository(Protocol):
    """Persist and retrieve durable companion memories."""

    async def save_memory(
        self,
        content: str,
        source_conversation_id: int | None = None,
        importance: int = 3,
        tags: Sequence[str] = (),
    ) -> MemoryEntry:
        """Persist one durable memory."""

    async def get_recent_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        """Return recent memories ordered newest first."""

    async def retrieve_relevant_memories(
        self,
        query: str,
        limit: int,
    ) -> tuple[MemoryEntry, ...]:
        """Return memories relevant to a user query."""

    async def delete_memory(self, memory_id: int) -> None:
        """Delete one memory."""
