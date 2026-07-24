"""Memory pipeline orchestration."""

from __future__ import annotations

from collections.abc import Sequence

from project_akiha.core.memory.extraction import (
    HeuristicMemoryExtractor,
    MemoryExtractor,
    MemorySourceMessage,
)
from project_akiha.core.memory.models import MemoryEntry
from project_akiha.core.memory.normalization import (
    DefaultMemoryNormalizer,
    MemoryNormalizer,
)
from project_akiha.core.memory.repository import MemoryRepository
from project_akiha.core.memory.validation import DefaultMemoryPolicy, MemoryPolicy


class MemoryPipeline:
    """Run extraction, normalization, validation, and storage."""

    def __init__(
        self,
        repository: MemoryRepository,
        extractor: MemoryExtractor | None = None,
        normalizer: MemoryNormalizer | None = None,
        policy: MemoryPolicy | None = None,
        duplicate_scan_limit: int = 100,
    ) -> None:
        self._repository = repository
        self._extractor = extractor or HeuristicMemoryExtractor()
        self._normalizer = normalizer or DefaultMemoryNormalizer()
        self._policy = policy or DefaultMemoryPolicy()
        self._duplicate_scan_limit = duplicate_scan_limit

    async def process_messages(
        self,
        messages: Sequence[MemorySourceMessage],
        source_conversation_id: int | None = None,
    ) -> tuple[MemoryEntry, ...]:
        """Extract, validate, and persist memories from messages."""
        candidates = tuple(
            self._normalizer.normalize(candidate)
            for candidate in self._extractor.extract(messages)
        )
        if not candidates:
            return ()

        existing_memories = await self._repository.get_recent_memories(
            self._duplicate_scan_limit
        )
        saved_memories: list[MemoryEntry] = []
        for candidate in candidates:
            if not self._policy.accepts(
                candidate,
                (*existing_memories, *saved_memories),
            ):
                continue

            saved_memory = await self._repository.save_memory(
                content=candidate.content,
                source_conversation_id=source_conversation_id,
                importance=candidate.importance,
                tags=candidate.tags,
            )
            saved_memories.append(saved_memory)

        return tuple(saved_memories)
