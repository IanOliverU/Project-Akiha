"""Memory pipeline orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from inspect import isawaitable

from project_akiha.core.memory.extraction import (
    HeuristicMemoryExtractor,
    MemoryExtractor,
    MemorySourceMessage,
)
from project_akiha.core.memory.models import MemoryCandidate, MemoryEntry
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

    def set_extractor(self, extractor: MemoryExtractor) -> None:
        """Replace the extractor used for future memory collection."""
        self._extractor = extractor

    async def process_messages(
        self,
        messages: Sequence[MemorySourceMessage],
        source_conversation_id: int | None = None,
    ) -> tuple[MemoryEntry, ...]:
        """Extract, validate, and persist memories from messages."""
        candidates = await self.collect_candidates(messages)
        saved_memories: list[MemoryEntry] = []
        for candidate in candidates:
            saved_memory = await self.save_candidate(
                candidate,
                source_conversation_id=source_conversation_id,
            )
            saved_memories.append(saved_memory)

        return tuple(saved_memories)

    async def collect_candidates(
        self,
        messages: Sequence[MemorySourceMessage],
    ) -> tuple[MemoryCandidate, ...]:
        """Extract, normalize, and validate memory candidates."""
        extracted_candidates = self._extractor.extract(messages)
        if isawaitable(extracted_candidates):
            extracted_candidates = await extracted_candidates

        extracted_candidates = tuple(
            self._normalizer.normalize(candidate) for candidate in extracted_candidates
        )
        return await self.validate_candidates(extracted_candidates)

    async def validate_candidates(
        self,
        candidates: Sequence[MemoryCandidate],
    ) -> tuple[MemoryCandidate, ...]:
        """Normalize and validate candidates without running extraction."""
        candidates = tuple(
            self._normalizer.normalize(candidate) for candidate in candidates
        )
        if not candidates:
            return ()

        existing_memories = await self._repository.get_recent_memories(
            self._duplicate_scan_limit
        )
        accepted_candidates: list[MemoryCandidate] = []
        for candidate in candidates:
            if not self._policy.accepts(
                candidate,
                (
                    *existing_memories,
                    *(
                        _candidate_to_memory_entry(accepted_candidate)
                        for accepted_candidate in accepted_candidates
                    ),
                ),
            ):
                continue

            accepted_candidates.append(candidate)

        return tuple(accepted_candidates)

    async def save_candidate(
        self,
        candidate: MemoryCandidate,
        source_conversation_id: int | None = None,
    ) -> MemoryEntry:
        """Persist one approved memory candidate."""
        return await self._repository.save_memory(
            content=candidate.content,
            source_conversation_id=source_conversation_id,
            importance=candidate.importance,
            tags=candidate.tags,
        )


def _candidate_to_memory_entry(candidate: MemoryCandidate) -> MemoryEntry:
    return MemoryEntry(
        id=0,
        content=candidate.content,
        source_conversation_id=None,
        importance=candidate.importance,
        tags=candidate.tags,
        created_at="",
        updated_at="",
        last_accessed_at=None,
    )
