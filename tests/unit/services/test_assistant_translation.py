"""Tests for provider-neutral assistant subtitle translation."""

from __future__ import annotations

import unittest
from collections.abc import AsyncIterator, Sequence

from project_akiha.core.memory import StoredMessage
from project_akiha.providers.ai import ChatMessage
from project_akiha.services.assistant_translation import AssistantTranslationService


class AssistantTranslationServiceTest(unittest.IsolatedAsyncioTestCase):
    """Verify isolated translation prompts and output cleanup."""

    async def test_translates_without_mutating_source_text(self) -> None:
        provider = _Provider("English translation: Good afternoon.")
        service = AssistantTranslationService(provider)
        source = "こんにちは。"

        translated = await service.translate_to_english(source)

        self.assertEqual(source, "こんにちは。")
        self.assertEqual(translated, "Good afternoon.")
        self.assertEqual(provider.messages[-1].role, "user")
        self.assertEqual(provider.messages[-1].content, source)
        self.assertIn(
            "Return only the English translation", provider.messages[0].content
        )

    async def test_cleans_fenced_translation(self) -> None:
        service = AssistantTranslationService(
            _Provider("```english\nPlease take a short rest.\n```")
        )

        translated = await service.translate_to_english("少し休んでください。")

        self.assertEqual(translated, "Please take a short rest.")

    async def test_rejects_empty_source_and_provider_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-empty"):
            await AssistantTranslationService(_Provider("unused")).translate_to_english(
                " "
            )

        with self.assertRaisesRegex(ValueError, "empty"):
            await AssistantTranslationService(_Provider(" ")).translate_to_english(
                "こんにちは。"
            )

    async def test_persists_translation_against_exact_message(self) -> None:
        repository = _Repository()
        service = AssistantTranslationService(
            _Provider("Hello."),
            repository,
        )

        translated = await service.translate_to_english("こんにちは。", message_id=42)

        self.assertEqual(translated, "Hello.")
        self.assertEqual(repository.saved, [(42, "Hello.")])


class _Provider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: tuple[ChatMessage, ...] = ()

    async def generate_response(self, messages: Sequence[ChatMessage]) -> str:
        self.messages = tuple(messages)
        return self.response

    async def stream_response(
        self,
        messages: Sequence[ChatMessage],
    ) -> AsyncIterator[str]:
        del messages
        if False:
            yield ""

    async def is_available(self) -> bool:
        return True


class _Repository:
    def __init__(self) -> None:
        self.saved: list[tuple[int, str]] = []

    async def save_message_translation(
        self,
        message_id: int,
        translation: str,
    ) -> StoredMessage:
        self.saved.append((message_id, translation))
        return StoredMessage(
            id=message_id,
            conversation_id=7,
            role="assistant",
            content="こんにちは。",
            created_at="now",
            english_translation=translation,
        )
