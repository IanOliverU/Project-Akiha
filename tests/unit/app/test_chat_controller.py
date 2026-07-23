"""Tests for the Phase 2 chat controller."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.app.chat_controller import ChatController
from project_akiha.providers.ai import MockAIProvider


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


if __name__ == "__main__":
    unittest.main()
