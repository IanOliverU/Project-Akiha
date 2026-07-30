"""Provider-neutral English subtitle translation for assistant replies."""

from __future__ import annotations

from project_akiha.core.memory import ConversationRepository
from project_akiha.providers.ai import AIProvider, ChatMessage

_TRANSLATION_INSTRUCTION = (
    "Translate the supplied Japanese assistant response into natural, concise "
    "English. Preserve names, facts, numbers, uncertainty, and safety guidance. "
    "Return only the English translation without labels, commentary, or Markdown."
)


class AssistantTranslationService:
    """Translate one completed response without changing canonical chat data."""

    def __init__(
        self,
        provider: AIProvider,
        repository: ConversationRepository | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository

    def apply_provider(self, provider: AIProvider) -> None:
        """Use an updated AI provider for future subtitle requests."""
        self._provider = provider

    async def translate_to_english(
        self,
        text: str,
        message_id: int | None = None,
    ) -> str:
        """Return a validated English subtitle for non-empty source text."""
        source = text.strip()
        if not source:
            raise ValueError("Translation requires non-empty source text.")

        translated = await self._provider.generate_response(
            (
                ChatMessage(role="system", content=_TRANSLATION_INSTRUCTION),
                ChatMessage(role="user", content=source),
            )
        )
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("Translation provider returned empty text.")
        cleaned = _clean_translation(translated)
        if self._repository is not None and message_id is not None:
            await self._repository.save_message_translation(message_id, cleaned)
        return cleaned


def _clean_translation(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3].strip()
        if cleaned.lower().startswith("english\n"):
            cleaned = cleaned.split("\n", maxsplit=1)[1].strip()
    for prefix in ("English translation:", "Translation:", "English:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix) :].strip()
            break
    if not cleaned:
        raise ValueError("Translation provider returned unusable text.")
    return cleaned
