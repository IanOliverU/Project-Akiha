-- Preserve existing timer metadata and all inbox records/issued identifiers.
CREATE TABLE notification_inbox_v16 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL CHECK (service IN ('gmail','discord','timers','reminders')),
    event_kind TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('critical','important','normal','low','silent')),
    display_text TEXT NOT NULL CHECK (length(display_text) BETWEEN 1 AND 320),
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    delivery_status TEXT NOT NULL CHECK (delivery_status IN ('pending','delivered','suppressed','silent','expired')),
    aggregate_count INTEGER NOT NULL DEFAULT 1 CHECK (aggregate_count BETWEEN 1 AND 100)
);
INSERT INTO notification_inbox_v16 SELECT * FROM notification_inbox;
UPDATE sqlite_sequence SET seq=max(seq,coalesce((SELECT seq FROM sqlite_sequence
    WHERE name='notification_inbox'),0)) WHERE name='notification_inbox_v16';
DROP TABLE notification_inbox;
ALTER TABLE notification_inbox_v16 RENAME TO notification_inbox;
CREATE INDEX idx_notification_inbox_created_at ON notification_inbox(created_at DESC);
CREATE INDEX idx_notification_inbox_unread ON notification_inbox(read_at,created_at DESC);
CREATE TABLE utility_reminders (
    reminder_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    label TEXT NOT NULL CHECK(length(label)<=64),
    timezone TEXT NOT NULL CHECK(length(timezone) BETWEEN 1 AND 64),
    created_at TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','elapsed','cancelled','missed')),
    completed_at TEXT,
    notification_id INTEGER
);
CREATE INDEX idx_utility_reminders_pending ON utility_reminders(status,due_at);
CREATE TABLE utility_reminder_snoozes (
    request_id TEXT PRIMARY KEY,
    request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
    reminder_id TEXT NOT NULL,
    due_at TEXT NOT NULL
);
