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
- memory enable/disable setting
- automatic memory pipeline runs after completed chat turns
- relevant memory retrieval before provider calls
- hidden memory context injection into system prompts
- configurable memory retrieval limit
- memory manager opened from Settings
- recent memory review
- delete selected memory
- clear all memories with confirmation
- optional memory approval before saving
- pending memory review, approve, reject, and clear actions
- `ConversationSummarizer` protocol
- deterministic closed-conversation summaries
- SQLite conversation `summary` storage through migration `0003_conversation_summaries.sql`
- recent closed-conversation summary retrieval
- hidden conversation-summary context injection into system prompts

## Not Yet In This Phase

- AI-assisted summary generation
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

The pipeline is wired into completed chat turns only. Failed or cancelled
responses do not create memories, and the feature can be disabled from Settings.

When a new chat is started, the previous conversation is closed with a compact
summary. The current implementation is deterministic and local; it records the
visible message count and the first user topics without sending transcript
content to an external summarizer.

Recent closed-conversation summaries can also be rendered into hidden prompt
context. This gives Akiha lightweight continuity across chats without replaying
raw transcripts.

## Memory Management

Settings can open the memory manager. The manager lists recent memories and can
delete one selected memory or clear all memories after confirmation.

When approval is enabled in Settings, extracted memory candidates are queued in
the Pending tab instead of being saved immediately. Pending memories can be
approved, rejected, or cleared.

## Prompt Context

Before provider calls, the current user message is used to retrieve relevant
memories. Retrieved memories are rendered into a hidden system prompt section
and are not added to visible chat history or transcript export.

When available, recent conversation summaries are added as a separate hidden
system prompt section. This is controlled by the same memory-enabled setting.
