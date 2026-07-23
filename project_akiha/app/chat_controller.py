"""Application controller for Phase 2 chat flow."""

from __future__ import annotations

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

    async def submit_user_message(self, content: str) -> ChatExchange:
        """Append a user message and return the assistant response."""
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("Chat message cannot be empty.")

        user_message = ChatMessage(role="user", content=normalized_content)
        self._messages.append(user_message)

        response = await self._ai_provider.generate_response(self.messages)
        assistant_message = ChatMessage(role="assistant", content=response)
        self._messages.append(assistant_message)

        return ChatExchange(
            user_message=user_message,
            assistant_message=assistant_message,
        )
