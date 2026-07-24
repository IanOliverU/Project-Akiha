ALTER TABLE memories
ADD COLUMN archived_at TEXT;

CREATE INDEX idx_memories_archived_updated
ON memories(archived_at, updated_at DESC, id DESC);
