CREATE TABLE IF NOT EXISTS behavior_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    kind TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_behavior_events_created_at
ON behavior_events(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_behavior_events_event_type
ON behavior_events(event_type);
