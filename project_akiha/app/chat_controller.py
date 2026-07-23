"""Application controller for Phase 2 chat flow."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from project_akiha.providers.ai import AIProvider, ChatMessage


@dataclass(frozen=True, slots=True)
class ChatExchange:
    """A completed user/assistant chat exchange."""

    user_message: ChatMessage
    assistant_message: ChatMessage


class ChatController:
    """Keep chat history and route messages through an AIProvider."""

    def __init__(self, ai_provider: AIProvider) -> None:
        self._ai_provider = ai_provider
        self._messages: list[ChatMessage] = []

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        """Return the current chat history."""
        return tuple(self._messages)

    def set_ai_provider(self, ai_provider: AIProvider) -> None:
        """Replace the provider used for future chat responses."""
        self._ai_provider = ai_provider

    async def submit_user_message(self, content: str) -> ChatExchange:
        """Append a user message and return the assistant response."""
        user_message = self._append_user_message(content)

        response = await self._ai_provider.generate_response(self.messages)
        assistant_message = self._append_assistant_message(response)

        return ChatExchange(
            user_message=user_message,
            assistant_message=assistant_message,
        )

    async def stream_user_message(self, content: str) -> AsyncIterator[str]:
        """Append a user message and yield the assistant response in chunks."""
        self._append_user_message(content)
        chunks: list[str] = []

        async for chunk in self._ai_provider.stream_response(self.messages):
            chunks.append(chunk)
            yield chunk

        self._append_assistant_message("".join(chunks))

    def _append_user_message(self, content: str) -> ChatMessage:
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Chat message cannot be empty.")

        user_message = ChatMessage(role="user", content=normalized_content)
        self._messages.append(user_message)
        return user_message

    def _append_assistant_message(self, response: str) -> ChatMessage:
        if not response.strip():
            raise ValueError("Assistant response cannot be empty.")

        assistant_message = ChatMessage(role="assistant", content=response)
        self._messages.append(assistant_message)
        return assistant_message
