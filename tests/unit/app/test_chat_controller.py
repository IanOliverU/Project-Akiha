"""Tests for the Phase 2 chat controller."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import AsyncIterator

from project_akiha.app.chat_controller import ChatController
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


async def _collect_stream(controller: ChatController, message: str) -> list[str]:
    return [chunk async for chunk in controller.stream_user_message(message)]


if __name__ == "__main__":
    unittest.main()
