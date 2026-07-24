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
- Local hashing embeddings for memory retrieval
- Vector-scored memory retrieval foundation
- Memory deletion
- Source conversation references
- `MemoryCandidate` model
- `MemoryExtractor` protocol
- `HeuristicMemoryExtractor`
- AI-assisted memory extraction with deterministic fallback
- `MemoryNormalizer` protocol and default implementation
- `MemoryPolicy` protocol and default validation policy
- `MemoryPipeline` orchestration for extraction, normalization, validation, and storage
- memory enable/disable setting
- automatic memory pipeline runs after completed chat turns
- relevant memory retrieval before provider calls
- hidden memory context injection into system prompts
- relationship/emotional memory modeling from retrieved memories
- hidden relationship context injection into system prompts
- configurable memory retrieval limit
- memory manager opened from Settings
- recent memory review
- saved memory search/filter UI
- saved memory editing
- saved memory importance and tag editing
- saved memory archiving
- archived memory review, search/filter, and restore
- delete selected memory
- clear all memories with confirmation
- optional memory approval before saving
- pending memory review, approve, reject, and clear actions
- pending memory search/filter UI
- `ConversationSummarizer` protocol
- deterministic closed-conversation summaries
- AI-assisted closed-conversation summaries with deterministic fallback
- SQLite conversation `summary` storage through migration `0003_conversation_summaries.sql`
- recent closed-conversation summary retrieval
- hidden conversation-summary context injection into system prompts

## Not Yet In This Phase

- external embedding providers
- persistent vector index beyond SQLite row storage
- autonomous reflection or learning jobs

## Storage

Memories are stored in the same local SQLite database as transcripts:

```text
%LOCALAPPDATA%\Akiha\akiha.sqlite3
```

The `memories` table is intentionally separate from `messages`. This keeps raw
history and durable remembered facts from becoming the same thing.

## Retrieval

The first retrieval path combines simple SQL storage with local scoring:

- recent memories by `updated_at`
- relevant memories by `content` or `tags_json` substring match
- local hashing embeddings stored as JSON
- vector similarity, lexical overlap, importance, and recency ranking

The current embedding provider is deterministic and dependency-free. It gives
the repository a vector-search shape now, while leaving room to replace it with
an external embedding provider or a dedicated vector index later.

## Pipeline

Memory is handled as a pipeline rather than one large service:

1. Extract candidates from user-authored messages.
2. Normalize content, tags, and importance.
3. Validate confidence, source role, specificity, and duplicates.
4. Store accepted memories through `MemoryRepository`.

The default extractor is deterministic and conservative. It recognizes explicit
requests like `remember that ...`, preference statements like `I prefer ...`,
and identity statements like `my name is ...`. When Ollama is configured, Akiha
uses AI-assisted extraction and falls back to the deterministic extractor if the
provider fails or returns invalid candidates.

The pipeline is wired into completed chat turns only. Failed or cancelled
responses do not create memories, and the feature can be disabled from Settings.

When a new chat is started, the previous conversation is closed with a compact
summary. The mock provider uses the deterministic local summarizer. When Ollama
is configured, Akiha uses an AI-assisted summarizer and falls back to the
deterministic summary if the provider fails or returns an empty result.

Recent closed-conversation summaries can also be rendered into hidden prompt
context. This gives Akiha lightweight continuity across chats without replaying
raw transcripts.

## Memory Management

Settings can open the memory manager. The manager lists recent memories and can
edit, archive, delete one selected memory, or clear all memories after confirmation.
Archived memories are excluded from active retrieval but can be reviewed and restored.

When approval is enabled in Settings, extracted memory candidates are queued in
the Pending tab instead of being saved immediately. Pending memories can be
approved, rejected, or cleared.

## Prompt Context

Before provider calls, the current user message is used to retrieve relevant
memories. Retrieved memories are rendered into a hidden system prompt section
and are not added to visible chat history or transcript export.

Relevant memories are also classified into relationship context such as identity,
preferences, goals, tools, boundaries, and emotional cues. This derived context
is rendered as a separate hidden prompt section so Akiha can respond with better
continuity without treating it as a separate persistent state.

When available, recent conversation summaries are added as a separate hidden
system prompt section. This is controlled by the same memory-enabled setting.
