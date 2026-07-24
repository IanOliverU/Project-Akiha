"""Tests for AI-assisted conversation summarization."""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator, Sequence

from project_akiha.providers.ai import ChatMessage
from project_akiha.services.conversation_summary import AIConversationSummarizer


class RecordingProvider:
    """AI provider test double that records prompt messages."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.messages: Sequence[ChatMessage] = ()

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        self.messages = messages
        return self._response

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        del messages
        yield self._response

    async def is_available(self) -> bool:
        return True


class FailingProvider:
    """AI provider test double that fails summarization calls."""

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        del messages
        raise RuntimeError("provider failed")

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        del messages
        raise RuntimeError("provider failed")
        yield ""

    async def is_available(self) -> bool:
        return False


class AIConversationSummarizerTest(unittest.IsolatedAsyncioTestCase):
    """Verify AI conversation summaries and fallback behavior."""

    async def test_uses_provider_to_summarize_visible_transcript(self) -> None:
        provider = RecordingProvider(" User planned Phase 3 memory work. ")
        summarizer = AIConversationSummarizer(provider)

        summary = await summarizer.summarize(
            (
                ChatMessage(role="system", content="hidden"),
                ChatMessage(role="user", content="Let's finish Phase 3."),
                ChatMessage(role="assistant", content="Good plan."),
            )
        )

        self.assertEqual(summary, "User planned Phase 3 memory work.")
        self.assertEqual(provider.messages[0].role, "system")
        self.assertEqual(provider.messages[1].role, "user")
        self.assertIn("user: Let's finish Phase 3.", provider.messages[1].content)
        self.assertNotIn("system: hidden", provider.messages[1].content)

    async def test_falls_back_when_provider_fails(self) -> None:
        summarizer = AIConversationSummarizer(FailingProvider())

        summary = await summarizer.summarize(
            (ChatMessage(role="user", content="Remember that I use Krita."),)
        )

        self.assertIn("Remember that I use Krita.", summary)

    async def test_falls_back_when_provider_returns_empty_summary(self) -> None:
        summarizer = AIConversationSummarizer(RecordingProvider("   "))

        summary = await summarizer.summarize(
            (ChatMessage(role="user", content="Remember that I use Krita."),)
        )

        self.assertIn("Remember that I use Krita.", summary)


if __name__ == "__main__":
    unittest.main()
