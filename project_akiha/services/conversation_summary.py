"""AI-assisted conversation summarization services."""

from __future__ import annotations

from collections.abc import Sequence

from project_akiha.core.memory import (
    HeuristicConversationSummarizer,
)
from project_akiha.core.memory.summarization import SummarySourceMessage
from project_akiha.providers.ai import AIProvider, ChatMessage


class AIConversationSummarizer:
    """Summarize closed conversations with an AI provider and deterministic fallback."""

    def __init__(
        self,
        ai_provider: AIProvider,
        fallback: HeuristicConversationSummarizer | None = None,
        max_transcript_characters: int = 4000,
    ) -> None:
        self._ai_provider = ai_provider
        self._fallback = fallback or HeuristicConversationSummarizer()
        self._max_transcript_characters = max_transcript_characters

    async def summarize(self, messages: Sequence[SummarySourceMessage]) -> str:
        """Return an AI summary, falling back when the provider cannot summarize."""
        fallback_summary = self._fallback.summarize(messages)
        transcript = _render_visible_transcript(messages)
        if not transcript:
            return ""

        try:
            summary = await self._ai_provider.generate_response(
                (
                    ChatMessage(
                        role="system",
                        content=(
                            "Summarize this closed desktop-companion conversation "
                            "for future continuity. Keep it concise, factual, and "
                            "focused on user goals, preferences, decisions, and "
                            "unfinished follow-ups. Do not invent details."
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=_clip_transcript(
                            transcript,
                            self._max_transcript_characters,
                        ),
                    ),
                )
            )
        except Exception:
            return fallback_summary

        normalized_summary = " ".join(summary.split())
        return normalized_summary or fallback_summary


def _render_visible_transcript(messages: Sequence[SummarySourceMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        if message.role == "system":
            continue
        content = " ".join(message.content.split())
        if content:
            lines.append(f"{message.role}: {content}")

    return "\n".join(lines)


def _clip_transcript(transcript: str, max_characters: int) -> str:
    if len(transcript) <= max_characters:
        return transcript

    return f"{transcript[: max_characters - 1].rstrip()}..."
