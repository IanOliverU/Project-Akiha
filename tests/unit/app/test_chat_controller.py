"""Tests for the Phase 2 chat controller."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator

from project_akiha.app.chat_controller import ChatController
from project_akiha.core.memory import (
    Conversation,
    ConversationSummary,
    MemoryCandidate,
    MemoryEntry,
    MessageRole,
    StoredMessage,
)
from project_akiha.providers.ai import ChatMessage, MockAIProvider


class StaticProvider:
    """Test provider that returns a configured response."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.generate_messages: tuple[ChatMessage, ...] = ()
        self.stream_messages: tuple[ChatMessage, ...] = ()

    async def generate_response(self, messages: tuple[ChatMessage, ...]) -> str:
        """Return the configured response."""
        self.generate_messages = messages
        return self._response

    async def stream_response(
        self,
        messages: tuple[ChatMessage, ...],
    ) -> AsyncIterator[str]:
        """Yield the configured response."""
        self.stream_messages = messages
        yield self._response

    async def is_available(self) -> bool:
        """Return true for test use."""
        return True


class FailingProvider:
    """Test provider that fails before producing a response."""

    async def generate_response(self, messages: tuple[ChatMessage, ...]) -> str:
        """Raise a provider failure."""
        del messages
        raise RuntimeError("provider failed")

    async def stream_response(
        self,
        messages: tuple[ChatMessage, ...],
    ) -> AsyncIterator[str]:
        """Raise a provider failure."""
        del messages
        raise RuntimeError("provider failed")
        yield ""

    async def is_available(self) -> bool:
        """Return false for test use."""
        return False


class RecordingConversationRepository:
    """Test repository that records saved messages."""

    def __init__(self) -> None:
        self.saved_messages: list[tuple[int, MessageRole, str]] = []
        self.export_messages: tuple[StoredMessage, ...] = ()
        self.conversation_summaries: tuple[ConversationSummary, ...] = ()
        self.summary_retrieval_calls: list[int] = []
        self.closed_conversation_ids: list[int] = []
        self.cleared_conversation_ids: list[int] = []
        self.next_conversation_id = 10

    async def create_conversation(self, title: str = "Current chat") -> Conversation:
        """Create a test conversation."""
        conversation = Conversation(
            id=self.next_conversation_id,
            title=title,
            created_at="now",
            updated_at="now",
            closed_at=None,
            summary=None,
        )
        self.next_conversation_id += 1
        return conversation

    async def get_or_create_current_conversation(self) -> Conversation:
        """Return a test conversation."""
        return Conversation(
            id=1,
            title="Test",
            created_at="now",
            updated_at="now",
            closed_at=None,
            summary=None,
        )

    async def close_conversation(
        self,
        conversation_id: int,
        summary: str | None = None,
    ) -> None:
        """Record a closed conversation."""
        del summary
        self.closed_conversation_ids.append(conversation_id)

    async def clear_conversation_messages(self, conversation_id: int) -> None:
        """Record a cleared conversation."""
        self.cleared_conversation_ids.append(conversation_id)

    async def save_message(
        self,
        conversation_id: int,
        role: MessageRole,
        content: str,
    ) -> StoredMessage:
        """Record a saved message."""
        self.saved_messages.append((conversation_id, role, content))
        return StoredMessage(
            id=len(self.saved_messages),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at="now",
        )

    async def get_recent_messages(
        self,
        conversation_id: int,
        limit: int,
    ) -> tuple[StoredMessage, ...]:
        """Return no persisted messages for test use."""
        del conversation_id, limit
        return ()

    async def get_messages(self, conversation_id: int) -> tuple[StoredMessage, ...]:
        """Return persisted messages for export."""
        del conversation_id
        return self.export_messages

    async def get_recent_conversation_summaries(
        self,
        limit: int,
    ) -> tuple[ConversationSummary, ...]:
        """Return configured conversation summaries."""
        self.summary_retrieval_calls.append(limit)
        return self.conversation_summaries


class RecordingMemoryPipeline:
    """Test memory pipeline that records processed messages."""

    def __init__(self) -> None:
        self.processed_messages: list[tuple[tuple[ChatMessage, ...], int | None]] = []
        self.candidates: tuple[MemoryCandidate, ...] = ()
        self.saved_candidates: list[tuple[MemoryCandidate, int | None]] = []

    async def process_messages(
        self,
        messages: tuple[ChatMessage, ...],
        source_conversation_id: int | None = None,
    ) -> tuple[object, ...]:
        """Record processed chat messages."""
        self.processed_messages.append((messages, source_conversation_id))
        return ()

    async def collect_candidates(
        self,
        messages: tuple[ChatMessage, ...],
    ) -> tuple[MemoryCandidate, ...]:
        """Return configured candidates."""
        del messages
        return self.candidates

    async def save_candidate(
        self,
        candidate: MemoryCandidate,
        source_conversation_id: int | None = None,
    ) -> MemoryEntry:
        """Record an approved candidate."""
        self.saved_candidates.append((candidate, source_conversation_id))
        return MemoryEntry(
            id=len(self.saved_candidates),
            content=candidate.content,
            source_conversation_id=source_conversation_id,
            importance=candidate.importance,
            tags=candidate.tags,
            created_at="now",
            updated_at="now",
            last_accessed_at=None,
        )


class RecordingMemoryRepository:
    """Test memory repository that records retrieval calls."""

    def __init__(self) -> None:
        self.relevant_memories: tuple[MemoryEntry, ...] = ()
        self.retrieval_calls: list[tuple[str, int]] = []

    async def save_memory(
        self,
        content: str,
        source_conversation_id: int | None = None,
        importance: int = 3,
        tags: tuple[str, ...] = (),
    ) -> MemoryEntry:
        """Return a saved test memory."""
        return MemoryEntry(
            id=1,
            content=content,
            source_conversation_id=source_conversation_id,
            importance=importance,
            tags=tuple(tags),
            created_at="now",
            updated_at="now",
            last_accessed_at=None,
        )

    async def get_recent_memories(self, limit: int) -> tuple[MemoryEntry, ...]:
        """Return no recent memories for test use."""
        del limit
        return ()

    async def retrieve_relevant_memories(
        self,
        query: str,
        limit: int,
    ) -> tuple[MemoryEntry, ...]:
        """Return configured relevant memories."""
        self.retrieval_calls.append((query, limit))
        return self.relevant_memories

    async def delete_memory(self, memory_id: int) -> None:
        """Ignore deletion for test use."""
        del memory_id


class ChatControllerTest(unittest.TestCase):
    """Verify chat history and provider routing."""

    def test_submit_user_message_records_exchange(self) -> None:
        controller = ChatController(MockAIProvider())

        exchange = asyncio.run(controller.submit_user_message(" hello "))

        self.assertEqual(exchange.user_message.content, "hello")
        self.assertEqual(exchange.assistant_message.role, "assistant")
        self.assertEqual(len(controller.messages), 2)

    def test_empty_message_is_rejected(self) -> None:
        controller = ChatController(MockAIProvider())

        with self.assertRaises(ValueError):
            asyncio.run(controller.submit_user_message("   "))

    def test_provider_can_be_replaced_for_future_messages(self) -> None:
        controller = ChatController(StaticProvider("first"))

        first_exchange = asyncio.run(controller.submit_user_message("hello"))
        controller.set_ai_provider(StaticProvider("second"))
        second_exchange = asyncio.run(controller.submit_user_message("again"))

        self.assertEqual(first_exchange.assistant_message.content, "first")
        self.assertEqual(second_exchange.assistant_message.content, "second")

    def test_stream_user_message_records_assistant_response(self) -> None:
        controller = ChatController(StaticProvider("streamed response"))

        chunks = asyncio.run(_collect_stream(controller, "hello"))

        self.assertEqual(chunks, ["streamed response"])
        self.assertEqual(controller.messages[-1].content, "streamed response")

    def test_system_prompt_is_sent_to_provider_only(self) -> None:
        provider = StaticProvider("hello from Akiha")
        controller = ChatController(provider, system_prompt="Stay warm.")

        asyncio.run(controller.submit_user_message("hello"))

        self.assertEqual(provider.generate_messages[0].role, "system")
        self.assertEqual(provider.generate_messages[0].content, "Stay warm.")
        self.assertEqual(provider.generate_messages[1].role, "user")
        self.assertEqual(provider.generate_messages[1].content, "hello")
        self.assertEqual(
            [message.role for message in controller.messages], ["user", "assistant"]
        )

    def test_system_prompt_can_be_replaced(self) -> None:
        provider = StaticProvider("done")
        controller = ChatController(provider, system_prompt="Old prompt.")

        controller.set_system_prompt("New prompt.")
        asyncio.run(_collect_stream(controller, "hello"))

        self.assertEqual(provider.stream_messages[0].content, "New prompt.")

    def test_messages_are_persisted_when_repository_is_configured(self) -> None:
        repository = RecordingConversationRepository()
        controller = ChatController(
            StaticProvider("hello from persistence"),
            conversation_repository=repository,
            conversation_id=7,
        )

        asyncio.run(controller.submit_user_message(" hello "))

        self.assertEqual(
            repository.saved_messages,
            [
                (7, "user", "hello"),
                (7, "assistant", "hello from persistence"),
            ],
        )

    def test_initial_system_messages_are_not_exposed_as_history(self) -> None:
        controller = ChatController(
            StaticProvider("done"),
            initial_messages=(
                ChatMessage(role="system", content="hidden"),
                ChatMessage(role="user", content="visible"),
            ),
        )

        self.assertEqual(
            controller.messages, (ChatMessage(role="user", content="visible"),)
        )

    def test_start_new_conversation_closes_current_and_clears_history(self) -> None:
        repository = RecordingConversationRepository()
        controller = ChatController(
            StaticProvider("done"),
            conversation_repository=repository,
            conversation_id=7,
            initial_messages=(ChatMessage(role="user", content="old"),),
        )

        asyncio.run(controller.start_new_conversation())
        asyncio.run(controller.submit_user_message("fresh"))

        self.assertEqual(repository.closed_conversation_ids, [7])
        self.assertEqual(controller.messages[0].content, "fresh")
        self.assertEqual(repository.saved_messages[0], (10, "user", "fresh"))

    def test_start_new_conversation_summarizes_closed_history(self) -> None:
        class RecordingSummarizer:
            def __init__(self) -> None:
                self.messages: tuple[ChatMessage, ...] = ()

            def summarize(self, messages: tuple[ChatMessage, ...]) -> str:
                self.messages = messages
                return "User planned the next feature."

        class SummaryRepository(RecordingConversationRepository):
            def __init__(self) -> None:
                super().__init__()
                self.closed_summaries: list[tuple[int, str | None]] = []

            async def close_conversation(
                self,
                conversation_id: int,
                summary: str | None = None,
            ) -> None:
                self.closed_summaries.append((conversation_id, summary))

        repository = SummaryRepository()
        summarizer = RecordingSummarizer()
        initial_messages = (
            ChatMessage(role="user", content="old request"),
            ChatMessage(role="assistant", content="old reply"),
        )
        controller = ChatController(
            StaticProvider("done"),
            conversation_repository=repository,
            conversation_id=7,
            initial_messages=initial_messages,
            conversation_summarizer=summarizer,
        )

        asyncio.run(controller.start_new_conversation())

        self.assertEqual(summarizer.messages, initial_messages)
        self.assertEqual(
            repository.closed_summaries,
            [(7, "User planned the next feature.")],
        )

    def test_start_new_conversation_supports_async_summarizer(self) -> None:
        class AsyncSummarizer:
            async def summarize(self, messages: tuple[ChatMessage, ...]) -> str:
                del messages
                return "Async summary."

        class SummaryRepository(RecordingConversationRepository):
            def __init__(self) -> None:
                super().__init__()
                self.closed_summaries: list[tuple[int, str | None]] = []

            async def close_conversation(
                self,
                conversation_id: int,
                summary: str | None = None,
            ) -> None:
                self.closed_summaries.append((conversation_id, summary))

        repository = SummaryRepository()
        controller = ChatController(
            StaticProvider("done"),
            conversation_repository=repository,
            conversation_id=7,
            initial_messages=(ChatMessage(role="user", content="old"),),
            conversation_summarizer=AsyncSummarizer(),
        )

        asyncio.run(controller.start_new_conversation())

        self.assertEqual(repository.closed_summaries, [(7, "Async summary.")])

    def test_start_new_conversation_clears_history_without_repository(self) -> None:
        controller = ChatController(
            StaticProvider("done"),
            initial_messages=(ChatMessage(role="user", content="old"),),
        )

        asyncio.run(controller.start_new_conversation())

        self.assertEqual(controller.messages, ())

    def test_clear_current_conversation_deletes_messages_and_clears_history(
        self,
    ) -> None:
        repository = RecordingConversationRepository()
        controller = ChatController(
            StaticProvider("done"),
            conversation_repository=repository,
            conversation_id=7,
            initial_messages=(ChatMessage(role="user", content="old"),),
        )

        asyncio.run(controller.clear_current_conversation())

        self.assertEqual(repository.cleared_conversation_ids, [7])
        self.assertEqual(controller.messages, ())

    def test_clear_current_conversation_clears_history_without_repository(self) -> None:
        controller = ChatController(
            StaticProvider("done"),
            initial_messages=(ChatMessage(role="user", content="old"),),
        )

        asyncio.run(controller.clear_current_conversation())

        self.assertEqual(controller.messages, ())

    def test_get_export_messages_uses_repository_when_available(self) -> None:
        repository = RecordingConversationRepository()
        repository.export_messages = (
            StoredMessage(
                id=1,
                conversation_id=7,
                role="user",
                content="from database",
                created_at="now",
            ),
            StoredMessage(
                id=2,
                conversation_id=7,
                role="assistant",
                content="stored reply",
                created_at="now",
            ),
        )
        controller = ChatController(
            StaticProvider("done"),
            conversation_repository=repository,
            conversation_id=7,
            initial_messages=(ChatMessage(role="user", content="memory only"),),
        )

        messages = asyncio.run(controller.get_export_messages())

        self.assertEqual(
            messages,
            (
                ChatMessage(role="user", content="from database"),
                ChatMessage(role="assistant", content="stored reply"),
            ),
        )

    def test_get_export_messages_falls_back_to_memory_without_repository(self) -> None:
        controller = ChatController(
            StaticProvider("done"),
            initial_messages=(ChatMessage(role="user", content="memory only"),),
        )

        self.assertEqual(
            asyncio.run(controller.get_export_messages()),
            (ChatMessage(role="user", content="memory only"),),
        )

    def test_submit_user_message_processes_memory_after_completed_exchange(
        self,
    ) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        controller = ChatController(
            StaticProvider("remembered"),
            conversation_id=7,
            memory_pipeline=memory_pipeline,
        )

        asyncio.run(controller.submit_user_message("Remember that I use Krita."))

        self.assertEqual(len(memory_pipeline.processed_messages), 1)
        messages, source_conversation_id = memory_pipeline.processed_messages[0]
        self.assertEqual(source_conversation_id, 7)
        self.assertEqual(
            messages,
            (
                ChatMessage(role="user", content="Remember that I use Krita."),
                ChatMessage(role="assistant", content="remembered"),
            ),
        )

    def test_memory_pipeline_is_skipped_when_disabled(self) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        controller = ChatController(
            StaticProvider("remembered"),
            memory_pipeline=memory_pipeline,
            memory_enabled=False,
        )

        asyncio.run(controller.submit_user_message("Remember that I use Krita."))

        self.assertEqual(memory_pipeline.processed_messages, [])

    def test_memory_pipeline_can_be_disabled_at_runtime(self) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        controller = ChatController(
            StaticProvider("remembered"),
            memory_pipeline=memory_pipeline,
        )

        controller.set_memory_enabled(False)
        asyncio.run(controller.submit_user_message("Remember that I use Krita."))

        self.assertEqual(memory_pipeline.processed_messages, [])

    def test_failed_provider_response_does_not_process_memory(self) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        controller = ChatController(
            FailingProvider(),
            memory_pipeline=memory_pipeline,
        )

        with self.assertRaises(RuntimeError):
            asyncio.run(controller.submit_user_message("Remember that I use Krita."))

        self.assertEqual(memory_pipeline.processed_messages, [])

    def test_memory_approval_queues_candidates_without_saving(self) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        memory_pipeline.candidates = (
            MemoryCandidate(
                content="User uses Krita.",
                source_role="user",
                importance=4,
                tags=("explicit",),
            ),
        )
        controller = ChatController(
            StaticProvider("remembered"),
            conversation_id=7,
            memory_pipeline=memory_pipeline,
            memory_requires_approval=True,
        )

        asyncio.run(controller.submit_user_message("Remember that I use Krita."))

        self.assertEqual(memory_pipeline.processed_messages, [])
        self.assertEqual(len(controller.pending_memories), 1)
        self.assertEqual(
            controller.pending_memories[0].candidate.content, "User uses Krita."
        )
        self.assertEqual(controller.pending_memories[0].source_conversation_id, 7)
        self.assertEqual(memory_pipeline.saved_candidates, [])

    def test_approve_pending_memory_saves_candidate(self) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        memory_pipeline.candidates = (
            MemoryCandidate(content="User uses Krita.", source_role="user"),
        )
        controller = ChatController(
            StaticProvider("remembered"),
            conversation_id=7,
            memory_pipeline=memory_pipeline,
            memory_requires_approval=True,
        )

        asyncio.run(controller.submit_user_message("Remember that I use Krita."))
        pending_memory_id = controller.pending_memories[0].id
        asyncio.run(controller.approve_pending_memory(pending_memory_id))

        self.assertEqual(controller.pending_memories, ())
        self.assertEqual(
            memory_pipeline.saved_candidates,
            [(MemoryCandidate(content="User uses Krita.", source_role="user"), 7)],
        )

    def test_reject_pending_memory_discards_candidate(self) -> None:
        memory_pipeline = RecordingMemoryPipeline()
        memory_pipeline.candidates = (
            MemoryCandidate(content="User uses Krita.", source_role="user"),
        )
        controller = ChatController(
            StaticProvider("remembered"),
            memory_pipeline=memory_pipeline,
            memory_requires_approval=True,
        )

        asyncio.run(controller.submit_user_message("Remember that I use Krita."))
        controller.reject_pending_memory(controller.pending_memories[0].id)

        self.assertEqual(controller.pending_memories, ())
        self.assertEqual(memory_pipeline.saved_candidates, [])

    def test_missing_pending_memory_is_rejected(self) -> None:
        controller = ChatController(StaticProvider("remembered"))

        with self.assertRaises(ValueError):
            controller.reject_pending_memory(999)

    def test_relevant_memories_are_sent_to_provider_system_prompt(self) -> None:
        provider = StaticProvider("done")
        memory_repository = RecordingMemoryRepository()
        memory_repository.relevant_memories = (
            MemoryEntry(
                id=1,
                content="User prefers concise replies.",
                source_conversation_id=None,
                importance=3,
                tags=("preference",),
                created_at="now",
                updated_at="now",
                last_accessed_at=None,
            ),
        )
        controller = ChatController(
            provider,
            system_prompt="Base persona.",
            memory_repository=memory_repository,
            memory_retrieval_limit=2,
        )

        asyncio.run(controller.submit_user_message("How should you answer?"))

        self.assertEqual(
            memory_repository.retrieval_calls,
            [("How should you answer?", 2)],
        )
        self.assertEqual(provider.generate_messages[0].role, "system")
        self.assertIn("Base persona.", provider.generate_messages[0].content)
        self.assertIn(
            "Relevant memories about the user:",
            provider.generate_messages[0].content,
        )
        self.assertIn(
            "User prefers concise replies.",
            provider.generate_messages[0].content,
        )
        self.assertEqual(
            [message.role for message in controller.messages], ["user", "assistant"]
        )

    def test_recent_conversation_summaries_are_sent_to_provider_system_prompt(
        self,
    ) -> None:
        provider = StaticProvider("done")
        conversation_repository = RecordingConversationRepository()
        conversation_repository.conversation_summaries = (
            ConversationSummary(
                id=3,
                title="Previous chat",
                summary="User discussed Phase 3 memory work.",
                created_at="then",
                updated_at="then",
                closed_at="then",
            ),
        )
        controller = ChatController(
            provider,
            conversation_repository=conversation_repository,
            conversation_id=7,
            memory_retrieval_limit=2,
        )

        asyncio.run(controller.submit_user_message("What were we doing?"))

        self.assertEqual(conversation_repository.summary_retrieval_calls, [2])
        self.assertEqual(provider.generate_messages[0].role, "system")
        self.assertIn(
            "Recent conversation summaries:",
            provider.generate_messages[0].content,
        )
        self.assertIn(
            "User discussed Phase 3 memory work.",
            provider.generate_messages[0].content,
        )
        self.assertEqual(
            [message.role for message in controller.messages], ["user", "assistant"]
        )

    def test_memory_context_is_skipped_when_memory_disabled(self) -> None:
        provider = StaticProvider("done")
        memory_repository = RecordingMemoryRepository()
        memory_repository.relevant_memories = (
            MemoryEntry(
                id=1,
                content="User prefers concise replies.",
                source_conversation_id=None,
                importance=3,
                tags=("preference",),
                created_at="now",
                updated_at="now",
                last_accessed_at=None,
            ),
        )
        controller = ChatController(
            provider,
            system_prompt="Base persona.",
            memory_repository=memory_repository,
            memory_enabled=False,
        )

        asyncio.run(controller.submit_user_message("How should you answer?"))

        self.assertEqual(memory_repository.retrieval_calls, [])
        self.assertEqual(provider.generate_messages[0].content, "Base persona.")

    def test_conversation_summary_context_is_skipped_when_memory_disabled(self) -> None:
        provider = StaticProvider("done")
        conversation_repository = RecordingConversationRepository()
        conversation_repository.conversation_summaries = (
            ConversationSummary(
                id=3,
                title="Previous chat",
                summary="User discussed Phase 3 memory work.",
                created_at="then",
                updated_at="then",
                closed_at="then",
            ),
        )
        controller = ChatController(
            provider,
            system_prompt="Base persona.",
            conversation_repository=conversation_repository,
            conversation_id=7,
            memory_enabled=False,
        )

        asyncio.run(controller.submit_user_message("What were we doing?"))

        self.assertEqual(conversation_repository.summary_retrieval_calls, [])
        self.assertEqual(provider.generate_messages[0].content, "Base persona.")

    def test_memory_retrieval_limit_can_be_updated(self) -> None:
        provider = StaticProvider("done")
        memory_repository = RecordingMemoryRepository()
        controller = ChatController(
            provider,
            memory_repository=memory_repository,
            memory_retrieval_limit=5,
        )

        controller.set_memory_retrieval_limit(1)
        asyncio.run(controller.submit_user_message("Any preference?"))

        self.assertEqual(memory_repository.retrieval_calls, [("Any preference?", 1)])

    def test_invalid_memory_retrieval_limit_is_rejected(self) -> None:
        controller = ChatController(StaticProvider("done"))

        with self.assertRaises(ValueError):
            controller.set_memory_retrieval_limit(0)


async def _collect_stream(controller: ChatController, message: str) -> list[str]:
    return [chunk async for chunk in controller.stream_user_message(message)]


if __name__ == "__main__":
    unittest.main()
