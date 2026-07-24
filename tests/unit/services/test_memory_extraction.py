"""Tests for AI-assisted memory extraction."""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator, Sequence

from project_akiha.providers.ai import ChatMessage
from project_akiha.services.memory_extraction import AIMemoryExtractor


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
    """AI provider test double that fails extraction calls."""

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


class AIMemoryExtractorTest(unittest.IsolatedAsyncioTestCase):
    """Verify AI memory extraction and fallback behavior."""

    async def test_parses_provider_json_candidates(self) -> None:
        provider = RecordingProvider("""
            [
              {
                "content": "User uses Krita.",
                "source_role": "user",
                "confidence": 0.92,
                "importance": 4,
                "tags": ["tool", "art"]
              }
            ]
            """)
        extractor = AIMemoryExtractor(provider)

        candidates = await extractor.extract(
            (
                ChatMessage(role="system", content="hidden"),
                ChatMessage(role="user", content="Remember that I use Krita."),
            )
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].content, "User uses Krita.")
        self.assertEqual(candidates[0].source_role, "user")
        self.assertEqual(candidates[0].confidence, 0.92)
        self.assertEqual(candidates[0].importance, 4)
        self.assertEqual(candidates[0].tags, ("tool", "art"))
        self.assertEqual(provider.messages[0].role, "system")
        self.assertIn("user: Remember that I use Krita.", provider.messages[1].content)
        self.assertNotIn("system: hidden", provider.messages[1].content)

    async def test_parses_fenced_json_payload(self) -> None:
        provider = RecordingProvider("""
            ```json
            [{"content": "User prefers concise replies.", "tags": ["preference"]}]
            ```
            """)
        extractor = AIMemoryExtractor(provider)

        candidates = await extractor.extract(
            (ChatMessage(role="user", content="I prefer concise replies."),)
        )

        self.assertEqual(candidates[0].content, "User prefers concise replies.")
        self.assertEqual(candidates[0].tags, ("preference",))

    async def test_falls_back_when_provider_fails(self) -> None:
        extractor = AIMemoryExtractor(FailingProvider())

        candidates = await extractor.extract(
            (ChatMessage(role="user", content="Remember that I use Krita."),)
        )

        self.assertEqual(candidates[0].content, "I use Krita")

    async def test_falls_back_when_provider_returns_invalid_json(self) -> None:
        extractor = AIMemoryExtractor(RecordingProvider("not json"))

        candidates = await extractor.extract(
            (ChatMessage(role="user", content="Remember that I use Krita."),)
        )

        self.assertEqual(candidates[0].content, "I use Krita")

    async def test_rejects_assistant_sourced_candidates(self) -> None:
        extractor = AIMemoryExtractor(
            RecordingProvider(
                '[{"content": "Assistant likes tea.", "source_role": "assistant"}]'
            )
        )

        candidates = await extractor.extract(
            (ChatMessage(role="assistant", content="I like tea."),)
        )

        self.assertEqual(candidates, ())


if __name__ == "__main__":
    unittest.main()
