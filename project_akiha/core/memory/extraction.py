"""Memory candidate extraction from chat messages."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Sequence
from typing import Protocol

from project_akiha.core.memory.models import MemoryCandidate, MessageRole


class MemorySourceMessage(Protocol):
    """Message shape accepted by memory extractors."""

    role: MessageRole
    content: str


class MemoryExtractor(Protocol):
    """Extract possible durable memories from chat messages."""

    def extract(
        self,
        messages: Sequence[MemorySourceMessage],
    ) -> tuple[MemoryCandidate, ...] | Awaitable[tuple[MemoryCandidate, ...]]:
        """Return memory candidates found in the given messages."""


class HeuristicMemoryExtractor:
    """Extract explicit memory candidates using deterministic text patterns."""

    _remember_pattern = re.compile(
        r"\bremember\s+(?:that\s+)?(?P<content>.+)",
        re.IGNORECASE,
    )
    _preference_patterns = (
        ("preference", re.compile(r"\bi\s+prefer\s+(?P<content>.+)", re.IGNORECASE)),
        ("preference", re.compile(r"\bi\s+like\s+(?P<content>.+)", re.IGNORECASE)),
        ("identity", re.compile(r"\bmy\s+name\s+is\s+(?P<content>.+)", re.IGNORECASE)),
    )
    _japanese_remember_patterns = (
        re.compile(
            r"(?:覚えておいて|覚えていて|覚えてください|記憶しておいて)"
            r"[\s、,:：]*(?P<content>.+)"
        ),
        re.compile(
            r"(?P<content>.+?)(?:を)?"
            r"(?:覚えておいて|覚えていて|覚えてください|記憶しておいて)$"
        ),
    )
    _japanese_identity_pattern = re.compile(
        r"(?:私|わたし|僕|ぼく|俺)の名前は[\s、]*(?P<content>.+)$"
    )
    _japanese_preference_pattern = re.compile(
        r"(?:私|わたし|僕|ぼく|俺)は[\s、]*(?P<content>.+?)"
        r"(?:が好き(?:です)?|を好みます|を好んでいます)$"
    )

    def extract(
        self,
        messages: Sequence[MemorySourceMessage],
    ) -> tuple[MemoryCandidate, ...]:
        """Return candidates from user-authored messages only."""
        candidates: list[MemoryCandidate] = []
        for message in messages:
            if message.role != "user":
                continue

            candidates.extend(_extract_from_user_text(message.content))

        return tuple(candidates)


def _extract_from_user_text(content: str) -> tuple[MemoryCandidate, ...]:
    text = _strip_terminal_punctuation(content.strip())
    if not text:
        return ()

    remember_match = HeuristicMemoryExtractor._remember_pattern.search(text)
    if remember_match is not None:
        return (
            MemoryCandidate(
                content=_sentence_case(remember_match.group("content")),
                source_role="user",
                confidence=0.95,
                importance=4,
                tags=("explicit",),
            ),
        )

    for pattern in HeuristicMemoryExtractor._japanese_remember_patterns:
        remember_match = pattern.search(text)
        if remember_match is not None:
            return (
                MemoryCandidate(
                    content=remember_match.group("content").strip(),
                    source_role="user",
                    confidence=0.95,
                    importance=4,
                    tags=("explicit",),
                ),
            )

    identity_match = HeuristicMemoryExtractor._japanese_identity_pattern.search(text)
    if identity_match is not None:
        name = _strip_japanese_copula(identity_match.group("content"))
        return (
            MemoryCandidate(
                content=f"ユーザーの名前は{name}です",
                source_role="user",
                confidence=0.8,
                importance=5,
                tags=("identity",),
            ),
        )

    preference_match = HeuristicMemoryExtractor._japanese_preference_pattern.search(
        text
    )
    if preference_match is not None:
        preference = preference_match.group("content").strip()
        return (
            MemoryCandidate(
                content=f"ユーザーは{preference}が好きです",
                source_role="user",
                confidence=0.8,
                importance=3,
                tags=("preference",),
            ),
        )

    for candidate_type, pattern in HeuristicMemoryExtractor._preference_patterns:
        match = pattern.search(text)
        if match is None:
            continue

        if candidate_type == "identity":
            content_text = f"User's name is {match.group('content')}"
            tags = ("identity",)
            importance = 5
        else:
            content_text = f"User prefers {match.group('content')}"
            tags = ("preference",)
            importance = 3

        return (
            MemoryCandidate(
                content=_sentence_case(content_text),
                source_role="user",
                confidence=0.8,
                importance=importance,
                tags=tags,
            ),
        )

    return ()


def _strip_terminal_punctuation(content: str) -> str:
    return content.strip().rstrip(" .!?。！？")


def _sentence_case(content: str) -> str:
    normalized = " ".join(content.split()).strip()
    if not normalized:
        return normalized
    return f"{normalized[0].upper()}{normalized[1:]}"


def _strip_japanese_copula(content: str) -> str:
    return re.sub(r"(?:です|だ)$", "", content.strip()).strip()
