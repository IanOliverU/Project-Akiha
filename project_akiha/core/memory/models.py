"""Domain models for conversation persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MessageRole = Literal["user", "assistant", "system"]


@dataclass(frozen=True, slots=True)
class Conversation:
    """A persisted chat session."""

    id: int
    title: str
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """A persisted message from a conversation transcript."""

    id: int
    conversation_id: int
    role: MessageRole
    content: str
    created_at: str


@dataclass(frozen=True, slots=True)
class MemoryEntry:
    """A durable fact or preference remembered from interaction."""

    id: int
    content: str
    source_conversation_id: int | None
    importance: int
    tags: tuple[str, ...]
    created_at: str
    updated_at: str
    last_accessed_at: str | None
