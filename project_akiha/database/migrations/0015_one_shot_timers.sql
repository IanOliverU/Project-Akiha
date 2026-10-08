-- Extend the existing inbox for local timer notifications, retaining its data.
CREATE TABLE notification_inbox_v15 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL CHECK (service IN ('gmail', 'discord', 'timers')),
    event_kind TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('critical','important','normal','low','silent')),
    display_text TEXT NOT NULL CHECK (length(display_text) BETWEEN 1 AND 320),
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    delivery_status TEXT NOT NULL CHECK (delivery_status IN ('pending','delivered','suppressed','silent','expired')),
    aggregate_count INTEGER NOT NULL DEFAULT 1 CHECK (aggregate_count BETWEEN 1 AND 100)
);
INSERT INTO notification_inbox_v15 SELECT * FROM notification_inbox;
-- Preserve issued IDs even when the owner's history was cleared earlier.
UPDATE sqlite_sequence
SET seq = max(seq, coalesce((SELECT seq FROM sqlite_sequence
                            WHERE name = 'notification_inbox'), 0))
WHERE name = 'notification_inbox_v15';
DROP TABLE notification_inbox;
ALTER TABLE notification_inbox_v15 RENAME TO notification_inbox;
CREATE INDEX idx_notification_inbox_created_at ON notification_inbox(created_at DESC);
CREATE INDEX idx_notification_inbox_unread ON notification_inbox(read_at, created_at DESC);

CREATE TABLE utility_timers (
    timer_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL CHECK (length(request_digest)=64),
    label TEXT NOT NULL CHECK (length(label)<=64),
    duration_seconds INTEGER NOT NULL CHECK (duration_seconds BETWEEN 1 AND 604800),
    created_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','elapsed','cancelled','missed')),
    completed_at TEXT,
    notification_id INTEGER
);
CREATE INDEX idx_utility_timers_pending ON utility_timers(status, due_at);
