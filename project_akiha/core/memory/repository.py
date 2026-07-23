"""Repository protocols for conversation persistence."""

from __future__ import annotations

from typing import Protocol

from project_akiha.core.memory.models import Conversation, MessageRole, StoredMessage


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
