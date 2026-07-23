"""Tests for the mock AI provider."""

from __future__ import annotations

import asyncio
import unittest

from project_akiha.providers.ai import ChatMessage, MockAIProvider


class MockAIProviderTest(unittest.TestCase):
    """Verify deterministic mock AI responses."""

    def test_response_mentions_latest_user_message(self) -> None:
        provider = MockAIProvider()

        response = asyncio.run(
            provider.generate_response(
                [
                    ChatMessage(role="user", content="hello"),
                    ChatMessage(role="assistant", content="old response"),
                    ChatMessage(role="user", content="are you there?"),
                ]
            )
        )

        self.assertEqual(response, "I heard you say: are you there?")

    def test_stream_response_yields_response_chunks(self) -> None:
        provider = MockAIProvider()

        chunks = asyncio.run(
            _collect_stream(
                provider,
                [ChatMessage(role="user", content="stream this")],
            )
        )

        self.assertEqual("".join(chunks), "I heard you say: stream this")

    def test_provider_is_available(self) -> None:
        provider = MockAIProvider()

        self.assertTrue(asyncio.run(provider.is_available()))


async def _collect_stream(
    provider: MockAIProvider,
    messages: list[ChatMessage],
) -> list[str]:
    return [chunk async for chunk in provider.stream_response(messages)]


if __name__ == "__main__":
    unittest.main()
