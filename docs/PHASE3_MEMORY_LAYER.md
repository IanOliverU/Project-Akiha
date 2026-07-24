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

## Not Yet In This Phase

- automatic memory extraction from messages
- memory review/approval UI
- prompt injection of relevant memories
- summarization of closed conversations
- embeddings or vector search

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
