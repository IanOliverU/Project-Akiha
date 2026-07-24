# Phase 3 Memory Layer

Phase 3 turns raw transcripts into durable memories. A transcript is the exact
conversation history; a memory is a curated fact or preference that can be
retrieved later and injected into prompts.

## Current Scope

- `MemoryEntry` domain model
- `MemoryRepository` protocol
- SQLite `memories` table through migration `0002_memories.sql`
- `SQLiteMemoryRepository`
- Recent memory retrieval
- Simple keyword/tag relevance retrieval
- Memory deletion
- Source conversation references
- `MemoryCandidate` model
- `MemoryExtractor` protocol
- `HeuristicMemoryExtractor`
- `MemoryNormalizer` protocol and default implementation
- `MemoryPolicy` protocol and default validation policy
- `MemoryPipeline` orchestration for extraction, normalization, validation, and storage

## Not Yet In This Phase

- memory review/approval UI
- prompt injection of relevant memories
- summarization of closed conversations
- embeddings or vector search
- chat integration for automatic pipeline runs after responses

## Storage

Memories are stored in the same local SQLite database as transcripts:

```text
%LOCALAPPDATA%\Akiha\akiha.sqlite3
```

The `memories` table is intentionally separate from `messages`. This keeps raw
history and durable remembered facts from becoming the same thing.

## Retrieval

The first retrieval path is simple SQL:

- recent memories by `updated_at`
- relevant memories by `content` or `tags_json` substring match
- relevance ordered by `importance`, then recency

This is enough for the first memory prompt-injection pass. Embeddings can be
added later behind the repository interface if simple retrieval becomes
insufficient.

## Pipeline

Memory is handled as a pipeline rather than one large service:

1. Extract candidates from user-authored messages.
2. Normalize content, tags, and importance.
3. Validate confidence, source role, specificity, and duplicates.
4. Store accepted memories through `MemoryRepository`.

The current extractor is deterministic and conservative. It recognizes explicit
requests like `remember that ...`, preference statements like `I prefer ...`,
and identity statements like `my name is ...`. Ollama-assisted extraction can
replace or augment this stage later without changing storage or retrieval.
