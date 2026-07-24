"""Application controller for Phase 2 chat flow."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from inspect import isawaitable

from project_akiha.core.memory import (
    ConversationRepository,
    ConversationSummarizer,
    ConversationSummaryContextAssembler,
    DefaultConversationSummaryContextAssembler,
    DefaultMemoryContextAssembler,
    HeuristicConversationSummarizer,
    MemoryContextAssembler,
    MemoryPipeline,
    MemoryRepository,
    PendingMemory,
)
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
        memory_repository: MemoryRepository | None = None,
        memory_context_assembler: MemoryContextAssembler | None = None,
        conversation_summary_context_assembler: (
            ConversationSummaryContextAssembler | None
        ) = None,
        memory_enabled: bool = True,
        memory_retrieval_limit: int = 5,
        memory_requires_approval: bool = False,
        conversation_summarizer: ConversationSummarizer | None = None,
    ) -> None:
        self._ai_provider = ai_provider
        self._system_prompt = system_prompt.strip()
        self._conversation_repository = conversation_repository
        self._conversation_id = conversation_id
        self._memory_pipeline = memory_pipeline
        self._memory_repository = memory_repository
        self._memory_context_assembler = (
            memory_context_assembler or DefaultMemoryContextAssembler()
        )
        self._conversation_summary_context_assembler = (
            conversation_summary_context_assembler
            or DefaultConversationSummaryContextAssembler()
        )
        self._memory_enabled = memory_enabled
        self._memory_retrieval_limit = memory_retrieval_limit
        self._memory_requires_approval = memory_requires_approval
        self._conversation_summarizer = (
            conversation_summarizer or HeuristicConversationSummarizer()
        )
        self._pending_memories: list[PendingMemory] = []
        self._next_pending_memory_id = 1
        self._messages: list[ChatMessage] = [
            message for message in initial_messages if message.role != "system"
        ]

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        """Return the current chat history."""
        return tuple(self._messages)

    @property
    def pending_memories(self) -> tuple[PendingMemory, ...]:
        """Return memories waiting for user approval."""
        return tuple(self._pending_memories)

    def set_ai_provider(self, ai_provider: AIProvider) -> None:
        """Replace the provider used for future chat responses."""
        self._ai_provider = ai_provider

    def set_conversation_summarizer(
        self,
        conversation_summarizer: ConversationSummarizer,
    ) -> None:
        """Replace the summarizer used for newly closed conversations."""
        self._conversation_summarizer = conversation_summarizer

    def set_system_prompt(self, system_prompt: str) -> None:
        """Replace the system prompt used for future chat responses."""
        self._system_prompt = system_prompt.strip()

    def set_memory_enabled(self, is_enabled: bool) -> None:
        """Set whether completed chat turns may create memories."""
        self._memory_enabled = is_enabled

    def set_memory_retrieval_limit(self, limit: int) -> None:
        """Set how many relevant memories may be injected into prompts."""
        if limit <= 0:
            raise ValueError("memory retrieval limit must be greater than zero.")
        self._memory_retrieval_limit = limit

    def set_memory_requires_approval(self, requires_approval: bool) -> None:
        """Set whether extracted memories wait for user approval."""
        self._memory_requires_approval = requires_approval

    async def approve_pending_memory(self, pending_memory_id: int) -> None:
        """Save one pending memory candidate."""
        pending_memory = self._pop_pending_memory(pending_memory_id)
        if self._memory_pipeline is None:
            return

        await self._memory_pipeline.save_candidate(
            pending_memory.candidate,
            source_conversation_id=pending_memory.source_conversation_id,
        )

    def reject_pending_memory(self, pending_memory_id: int) -> None:
        """Discard one pending memory candidate."""
        self._pop_pending_memory(pending_memory_id)

    def clear_pending_memories(self) -> None:
        """Discard all pending memory candidates."""
        self._pending_memories.clear()

    async def start_new_conversation(self) -> None:
        """Close the current conversation and begin a fresh transcript."""
        if self._conversation_repository is None:
            self._messages.clear()
            return

        if self._conversation_id is not None:
            summary = await self._summarize_current_conversation()
            await self._conversation_repository.close_conversation(
                self._conversation_id,
                summary=summary or None,
            )

        conversation = await self._conversation_repository.create_conversation()
        self._conversation_id = conversation.id
        self._messages.clear()

    async def _summarize_current_conversation(self) -> str:
        summary = self._conversation_summarizer.summarize(self.messages)
        if isawaitable(summary):
            return await summary
        return summary

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

        provider_messages = await self._messages_for_provider(user_message.content)
        response = await self._ai_provider.generate_response(provider_messages)
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

        provider_messages = await self._messages_for_provider(user_message.content)
        async for chunk in self._ai_provider.stream_response(provider_messages):
            chunks.append(chunk)
            yield chunk

        assistant_message = self._append_assistant_message("".join(chunks))
        await self._persist_message(assistant_message)
        await self._process_memory((user_message, assistant_message))

    async def _messages_for_provider(self, user_query: str) -> tuple[ChatMessage, ...]:
        system_prompt = await self._render_system_prompt(user_query)
        if not system_prompt:
            return self.messages

        return (
            ChatMessage(role="system", content=system_prompt),
            *self._messages,
        )

    async def _render_system_prompt(self, user_query: str) -> str:
        parts = [self._system_prompt] if self._system_prompt else []
        memory_context = await self._render_memory_context(user_query)
        if memory_context:
            parts.append(memory_context)
        conversation_summary_context = await self._render_conversation_summary_context()
        if conversation_summary_context:
            parts.append(conversation_summary_context)
        return "\n\n".join(parts)

    async def _render_memory_context(self, user_query: str) -> str:
        if (
            not self._memory_enabled
            or self._memory_repository is None
            or not user_query.strip()
        ):
            return ""

        memories = await self._memory_repository.retrieve_relevant_memories(
            user_query,
            limit=self._memory_retrieval_limit,
        )
        return self._memory_context_assembler.assemble(memories)

    async def _render_conversation_summary_context(self) -> str:
        if not self._memory_enabled or self._conversation_repository is None:
            return ""

        summaries = (
            await self._conversation_repository.get_recent_conversation_summaries(
                limit=self._memory_retrieval_limit,
            )
        )
        return self._conversation_summary_context_assembler.assemble(summaries)

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

        if not self._memory_requires_approval:
            await self._memory_pipeline.process_messages(
                messages,
                source_conversation_id=self._conversation_id,
            )
            return

        candidates = await self._memory_pipeline.collect_candidates(messages)
        for candidate in candidates:
            self._pending_memories.append(
                PendingMemory(
                    id=self._next_pending_memory_id,
                    candidate=candidate,
                    source_conversation_id=self._conversation_id,
                )
            )
            self._next_pending_memory_id += 1

    def _pop_pending_memory(self, pending_memory_id: int) -> PendingMemory:
        for index, pending_memory in enumerate(self._pending_memories):
            if pending_memory.id == pending_memory_id:
                return self._pending_memories.pop(index)

        raise ValueError("pending memory was not found.")
