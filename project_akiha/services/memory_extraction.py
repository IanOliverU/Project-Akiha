"""AI-assisted memory extraction services."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from project_akiha.core.memory import MemoryCandidate
from project_akiha.core.memory.extraction import (
    HeuristicMemoryExtractor,
    MemorySourceMessage,
)
from project_akiha.providers.ai import AIProvider, ChatMessage


class AIMemoryExtractor:
    """Extract memory candidates with an AI provider and deterministic fallback."""

    def __init__(
        self,
        ai_provider: AIProvider,
        fallback: HeuristicMemoryExtractor | None = None,
        max_transcript_characters: int = 4000,
    ) -> None:
        self._ai_provider = ai_provider
        self._fallback = fallback or HeuristicMemoryExtractor()
        self._max_transcript_characters = max_transcript_characters

    async def extract(
        self,
        messages: Sequence[MemorySourceMessage],
    ) -> tuple[MemoryCandidate, ...]:
        """Return AI-extracted candidates, falling back when extraction fails."""
        fallback_candidates = self._fallback.extract(messages)
        transcript = _render_visible_transcript(messages)
        if not transcript:
            return ()

        try:
            response = await self._ai_provider.generate_response(
                (
                    ChatMessage(
                        role="system",
                        content=(
                            "Extract durable user memories from this conversation. "
                            "Return only JSON: an array of objects with content, "
                            "confidence, importance, and tags. Use source_role "
                            '"user" only. Include stable user facts, preferences, '
                            "identity, tools, goals, and constraints. Ignore "
                            "assistant claims, transient chatter, and uncertain "
                            "details."
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
            candidates = _parse_candidates(response)
        except Exception:
            return fallback_candidates

        return candidates or fallback_candidates


def _render_visible_transcript(messages: Sequence[MemorySourceMessage]) -> str:
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


def _parse_candidates(response: str) -> tuple[MemoryCandidate, ...]:
    payload = json.loads(_extract_json_payload(response))
    if not isinstance(payload, list):
        return ()

    candidates: list[MemoryCandidate] = []
    for item in payload:
        candidate = _candidate_from_item(item)
        if candidate is not None:
            candidates.append(candidate)

    return tuple(candidates)


def _candidate_from_item(item: Any) -> MemoryCandidate | None:
    if not isinstance(item, dict):
        return None

    content = str(item.get("content", "")).strip()
    if not content:
        return None

    source_role = str(item.get("source_role", "user")).strip().lower()
    if source_role != "user":
        return None

    confidence = _coerce_float(item.get("confidence", 0.8), default=0.8)
    importance = int(_coerce_float(item.get("importance", 3), default=3))
    tags = _coerce_tags(item.get("tags", ()))
    return MemoryCandidate(
        content=content,
        source_role="user",
        confidence=confidence,
        importance=importance,
        tags=tags,
    )


def _extract_json_payload(response: str) -> str:
    stripped = response.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    start = stripped.find("[")
    end = stripped.rfind("]")
    if start == -1 or end == -1 or end < start:
        return stripped

    return stripped[start : end + 1]


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_tags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()

    return tuple(str(tag).strip() for tag in value if str(tag).strip())
