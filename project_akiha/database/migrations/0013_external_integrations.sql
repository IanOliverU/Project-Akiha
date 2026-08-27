CREATE TABLE IF NOT EXISTS external_event_receipts (
    service TEXT NOT NULL CHECK (service IN ('gmail', 'discord')),
    external_id_hash TEXT NOT NULL CHECK (length(external_id_hash) = 64),
    event_kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    classification TEXT NOT NULL,
    priority TEXT NOT NULL,
    notification_status TEXT NOT NULL CHECK (
        notification_status IN (
            'received', 'queued', 'delivered', 'suppressed', 'silent', 'expired'
        )
    ),
    notified_at TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (service, external_id_hash)
);

CREATE INDEX IF NOT EXISTS idx_external_event_receipts_created_at
ON external_event_receipts(created_at DESC);

CREATE TABLE IF NOT EXISTS integration_sync_state (
    service TEXT NOT NULL CHECK (service IN ('gmail', 'discord')),
    account_key_hash TEXT NOT NULL CHECK (length(account_key_hash) = 64),
    cursor TEXT NOT NULL,
    last_successful_sync_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (service, account_key_hash)
);
