"""Tests for the Ollama AI provider."""

from __future__ import annotations

import asyncio
import unittest
from typing import Any

from project_akiha.providers.ai import ChatMessage, OllamaProvider, OllamaProviderError


class OllamaProviderTest(unittest.TestCase):
    """Verify Ollama payload construction and response parsing."""

    def test_generate_response_posts_chat_payload(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            url: str,
            payload: dict[str, Any],
            timeout_seconds: float,
        ) -> dict[str, Any]:
            captured["url"] = url
            captured["payload"] = payload
            captured["timeout_seconds"] = timeout_seconds
            return {"message": {"content": "hello from ollama"}}

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            timeout_seconds=12.0,
            transport=transport,
        )

        response = asyncio.run(
            provider.generate_response([ChatMessage(role="user", content="hi")])
        )

        self.assertEqual(response, "hello from ollama")
        self.assertEqual(captured["url"], "http://localhost:11434/api/chat")
        self.assertEqual(captured["payload"]["model"], "akiha-test")
        self.assertFalse(captured["payload"]["stream"])
        self.assertEqual(captured["timeout_seconds"], 12.0)

    def test_invalid_response_raises_provider_error(self) -> None:
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            transport=lambda _url, _payload, _timeout: {"message": {}},
        )

        with self.assertRaises(OllamaProviderError):
            asyncio.run(
                provider.generate_response([ChatMessage(role="user", content="hi")])
            )

    def test_is_available_returns_false_on_provider_error(self) -> None:
        def transport(
            _url: str,
            _payload: dict[str, Any],
            _timeout_seconds: float,
        ) -> dict[str, Any]:
            raise OllamaProviderError("offline")

        provider = OllamaProvider(
            base_url="http://localhost:11434",
            model="akiha-test",
            transport=transport,
        )

        self.assertFalse(asyncio.run(provider.is_available()))


if __name__ == "__main__":
    unittest.main()
