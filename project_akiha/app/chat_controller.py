"""Application controller for Phase 2 chat flow."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from project_akiha.core.memory import ConversationRepository, MemoryPipeline
from project_akiha.providers.ai import AIProvider, ChatMessage


@dataclass(frozen=True, slots=True)
class ChatExchange:
    """A completed user/assistant chat exchange."""

    user_message: ChatMessage
    assistant_message: ChatMessage


class ChatController:
    """Keep chat history and route messages through an AIProvider."""

    def __init__(
        self,
        ai_provider: AIProvider,
        system_prompt: str = "",
        conversation_repository: ConversationRepository | None = None,
        conversation_id: int | None = None,
        initial_messages: tuple[ChatMessage, ...] = (),
        memory_pipeline: MemoryPipeline | None = None,
        memory_enabled: bool = True,
    ) -> None:
        self._ai_provider = ai_provider
        self._system_prompt = system_prompt.strip()
        self._conversation_repository = conversation_repository
        self._conversation_id = conversation_id
        self._memory_pipeline = memory_pipeline
        self._memory_enabled = memory_enabled
        self._messages: list[ChatMessage] = [
            message for message in initial_messages if message.role != "system"
        ]

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        """Return the current chat history."""
        return tuple(self._messages)

    def set_ai_provider(self, ai_provider: AIProvider) -> None:
        """Replace the provider used for future chat responses."""
        self._ai_provider = ai_provider

    def set_system_prompt(self, system_prompt: str) -> None:
        """Replace the system prompt used for future chat responses."""
        self._system_prompt = system_prompt.strip()

    def set_memory_enabled(self, is_enabled: bool) -> None:
        """Set whether completed chat turns may create memories."""
        self._memory_enabled = is_enabled

    async def start_new_conversation(self) -> None:
        """Close the current conversation and begin a fresh transcript."""
        if self._conversation_repository is None:
            self._messages.clear()
            return

        if self._conversation_id is not None:
            await self._conversation_repository.close_conversation(
                self._conversation_id
            )

        conversation = await self._conversation_repository.create_conversation()
        self._conversation_id = conversation.id
        self._messages.clear()

    async def clear_current_conversation(self) -> None:
        """Clear the current transcript without starting a new conversation."""
        if (
            self._conversation_repository is not None
            and self._conversation_id is not None
        ):
            await self._conversation_repository.clear_conversation_messages(
                self._conversation_id
            )

        self._messages.clear()

    async def get_export_messages(self) -> tuple[ChatMessage, ...]:
        """Return the full current transcript for export."""
        if self._conversation_repository is None or self._conversation_id is None:
            return self.messages

        stored_messages = await self._conversation_repository.get_messages(
            self._conversation_id
        )
        return tuple(
            ChatMessage(role=message.role, content=message.content)
            for message in stored_messages
            if message.role != "system"
        )

    async def submit_user_message(self, content: str) -> ChatExchange:
        """Append a user message and return the assistant response."""
        user_message = self._append_user_message(content)
        await self._persist_message(user_message)

        response = await self._ai_provider.generate_response(
            self._messages_for_provider()
        )
        assistant_message = self._append_assistant_message(response)
        await self._persist_message(assistant_message)
        await self._process_memory((user_message, assistant_message))

        return ChatExchange(
            user_message=user_message,
            assistant_message=assistant_message,
        )

    async def stream_user_message(self, content: str) -> AsyncIterator[str]:
        """Append a user message and yield the assistant response in chunks."""
        user_message = self._append_user_message(content)
        await self._persist_message(user_message)
        chunks: list[str] = []

        async for chunk in self._ai_provider.stream_response(
            self._messages_for_provider()
        ):
            chunks.append(chunk)
            yield chunk

        assistant_message = self._append_assistant_message("".join(chunks))
        await self._persist_message(assistant_message)
        await self._process_memory((user_message, assistant_message))

    def _messages_for_provider(self) -> tuple[ChatMessage, ...]:
        if not self._system_prompt:
            return self.messages

        return (
            ChatMessage(role="system", content=self._system_prompt),
            *self._messages,
        )

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

    async def _persist_message(self, message: ChatMessage) -> None:
        if self._conversation_repository is None or self._conversation_id is None:
            return

        await self._conversation_repository.save_message(
            conversation_id=self._conversation_id,
            role=message.role,
            content=message.content,
        )

    async def _process_memory(self, messages: tuple[ChatMessage, ...]) -> None:
        if not self._memory_enabled or self._memory_pipeline is None:
            return

        await self._memory_pipeline.process_messages(
            messages,
            source_conversation_id=self._conversation_id,
        )
