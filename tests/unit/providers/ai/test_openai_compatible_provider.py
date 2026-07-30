"""Tests for OpenAI-compatible hosted chat providers."""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Iterable, Mapping
from typing import Any

from project_akiha.providers.ai import (
    ChatMessage,
    OpenAICompatibleProvider,
    OpenAICompatibleProviderError,
    UnavailableAIProvider,
)


class OpenAICompatibleProviderTest(unittest.TestCase):
    """Verify shared Chat Completions requests and parsing."""

    def test_generate_response_posts_model_messages_and_bearer_key(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            url: str,
            payload: dict[str, Any],
            headers: Mapping[str, str],
            timeout: float,
        ) -> dict[str, Any]:
            captured.update(
                url=url,
                payload=payload,
                headers=dict(headers),
                timeout=timeout,
            )
            return {"choices": [{"message": {"content": "Hello from Gemini."}}]}

        provider = OpenAICompatibleProvider(
            base_url="https://example.test/v1/",
            model="test-model",
            api_key="secret-key",
            timeout_seconds=12,
            transport=transport,
        )

        response = asyncio.run(
            provider.generate_response([ChatMessage(role="user", content="Hello")])
        )

        self.assertEqual(response, "Hello from Gemini.")
        self.assertEqual(
            captured["url"],
            "https://example.test/v1/chat/completions",
        )
        self.assertEqual(captured["payload"]["model"], "test-model")
        self.assertFalse(captured["payload"]["stream"])
        self.assertEqual(
            captured["payload"]["messages"],
            [{"role": "user", "content": "Hello"}],
        )
        self.assertEqual(
            captured["headers"]["Authorization"],
            "Bearer secret-key",
        )
        self.assertEqual(captured["timeout"], 12)

    def test_stream_response_yields_text_and_ignores_null_content(self) -> None:
        captured: dict[str, Any] = {}

        def stream_transport(
            url: str,
            payload: dict[str, Any],
            headers: Mapping[str, str],
            timeout: float,
        ) -> Iterable[dict[str, Any]]:
            captured.update(url=url, payload=payload, headers=dict(headers))
            return (
                {"choices": [{"delta": {"content": "Good"}}]},
                {"choices": [{"delta": {"content": None}}]},
                {"choices": [{"delta": {"content": " evening."}}]},
            )

        provider = OpenAICompatibleProvider(
            base_url="https://example.test/v1",
            model="test-model",
            stream_transport=stream_transport,
        )

        chunks = asyncio.run(
            _collect_stream(
                provider,
                [ChatMessage(role="user", content="Hello")],
            )
        )

        self.assertEqual(chunks, ["Good", " evening."])
        self.assertTrue(captured["payload"]["stream"])
        self.assertNotIn("Authorization", captured["headers"])

    def test_is_available_uses_models_endpoint(self) -> None:
        captured: list[str] = []

        def health_transport(
            url: str,
            headers: Mapping[str, str],
            timeout: float,
        ) -> None:
            del headers, timeout
            captured.append(url)

        provider = OpenAICompatibleProvider(
            base_url="https://example.test/v1",
            model="test-model",
            health_transport=health_transport,
        )

        self.assertTrue(asyncio.run(provider.is_available()))
        self.assertEqual(captured, ["https://example.test/v1/models"])

    def test_generate_response_names_provider_in_transport_error(self) -> None:
        def transport(
            url: str,
            payload: dict[str, Any],
            headers: Mapping[str, str],
            timeout: float,
        ) -> dict[str, Any]:
            del url, payload, headers, timeout
            raise OpenAICompatibleProviderError(
                "The hosted AI rate limit or quota was reached."
            )

        provider = OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            model="gpt-5-mini",
            provider_name="openai",
            transport=transport,
        )

        with self.assertRaisesRegex(
            OpenAICompatibleProviderError,
            "OpenAI rate limit or quota was reached",
        ):
            asyncio.run(
                provider.generate_response([ChatMessage(role="user", content="Hello")])
            )

    def test_generate_response_names_grok_in_transport_error(self) -> None:
        def transport(
            url: str,
            payload: dict[str, Any],
            headers: Mapping[str, str],
            timeout: float,
        ) -> dict[str, Any]:
            del url, payload, headers, timeout
            raise OpenAICompatibleProviderError("The hosted AI API key was rejected.")

        provider = OpenAICompatibleProvider(
            base_url="https://api.x.ai/v1",
            model="grok-4.5",
            provider_name="grok",
            transport=transport,
        )

        with self.assertRaisesRegex(
            OpenAICompatibleProviderError,
            "Grok API key was rejected",
        ):
            asyncio.run(
                provider.generate_response([ChatMessage(role="user", content="Hello")])
            )

    def test_unavailable_provider_never_accepts_message_content(self) -> None:
        provider = UnavailableAIProvider("API key missing.")

        with self.assertRaisesRegex(
            OpenAICompatibleProviderError,
            "API key missing",
        ):
            asyncio.run(
                provider.generate_response(
                    [ChatMessage(role="user", content="private message")]
                )
            )

        self.assertFalse(asyncio.run(provider.is_available()))


async def _collect_stream(
    provider: OpenAICompatibleProvider,
    messages: list[ChatMessage],
) -> list[str]:
    return [chunk async for chunk in provider.stream_response(messages)]


if __name__ == "__main__":
    unittest.main()
