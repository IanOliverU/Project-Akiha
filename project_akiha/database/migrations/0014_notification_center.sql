CREATE TABLE IF NOT EXISTS notification_inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL CHECK (service IN ('gmail', 'discord')),
    event_kind TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (
        priority IN ('critical', 'important', 'normal', 'low', 'silent')
    ),
    display_text TEXT NOT NULL CHECK (
        length(display_text) BETWEEN 1 AND 320
    ),
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    read_at TEXT,
    delivery_status TEXT NOT NULL CHECK (
        delivery_status IN ('pending', 'delivered', 'suppressed', 'silent', 'expired')
    ),
    aggregate_count INTEGER NOT NULL DEFAULT 1 CHECK (
        aggregate_count BETWEEN 1 AND 100
    )
);

CREATE INDEX IF NOT EXISTS idx_notification_inbox_created_at
ON notification_inbox(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_notification_inbox_unread
ON notification_inbox(read_at, created_at DESC);
