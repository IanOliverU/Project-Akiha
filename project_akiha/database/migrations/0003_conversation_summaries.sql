ALTER TABLE conversations
ADD COLUMN summary TEXT;

CREATE INDEX idx_conversations_summary_updated
ON conversations(updated_at DESC)
WHERE summary IS NOT NULL;
