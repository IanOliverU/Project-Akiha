CREATE TABLE schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_conversations_open_updated
ON conversations(closed_at, updated_at);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
ON messages(conversation_id, created_at, id);

INSERT INTO schema_version(version,name) VALUES (1,'conversation_transcripts');
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    source_conversation_id INTEGER,
    importance INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed_at TEXT,
    FOREIGN KEY (source_conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_updated
ON memories(updated_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_memories_importance
ON memories(importance DESC, updated_at DESC);

INSERT INTO schema_version(version,name) VALUES (2,'memories');
ALTER TABLE conversations
ADD COLUMN summary TEXT;

CREATE INDEX idx_conversations_summary_updated
ON conversations(updated_at DESC)
WHERE summary IS NOT NULL;

INSERT INTO schema_version(version,name) VALUES (3,'conversation_summaries');
ALTER TABLE memories
ADD COLUMN archived_at TEXT;

CREATE INDEX idx_memories_archived_updated
ON memories(archived_at, updated_at DESC, id DESC);

INSERT INTO schema_version(version,name) VALUES (4,'memory_archiving');
ALTER TABLE memories
ADD COLUMN embedding_json TEXT;

INSERT INTO schema_version(version,name) VALUES (5,'memory_embeddings');
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

INSERT INTO schema_version(version,name) VALUES (6,'behavior_events');
ALTER TABLE messages
ADD COLUMN english_translation TEXT;

INSERT INTO schema_version(version,name) VALUES (7,'message_translations');
CREATE TABLE IF NOT EXISTS assistant_action_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability TEXT NOT NULL,
    target TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_action_permissions_active_scope
ON assistant_action_permissions(capability, target)
WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_action_permissions_capability
ON assistant_action_permissions(capability, revoked_at, id DESC);

CREATE TABLE IF NOT EXISTS assistant_action_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    action_id TEXT NOT NULL,
    source TEXT NOT NULL,
    normalized_target TEXT,
    permission_decision TEXT NOT NULL,
    result_status TEXT NOT NULL,
    duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
    failure_category TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_action_audit_created_at
ON assistant_action_audit(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_action_audit_action
ON assistant_action_audit(action_id, result_status, id DESC);

INSERT INTO schema_version(version,name) VALUES (8,'assistant_actions');
CREATE TABLE IF NOT EXISTS pet_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    satiety INTEGER NOT NULL CHECK(satiety BETWEEN 0 AND 100),
    energy INTEGER NOT NULL CHECK(energy BETWEEN 0 AND 100),
    attention INTEGER NOT NULL CHECK(attention BETWEEN 0 AND 100),
    affection INTEGER NOT NULL CHECK(affection BETWEEN 0 AND 100),
    xp INTEGER NOT NULL CHECK(xp >= 0),
    level INTEGER NOT NULL CHECK(level >= 1),
    currency INTEGER NOT NULL CHECK(currency >= 0),
    satiety_decay_seconds INTEGER NOT NULL CHECK(satiety_decay_seconds >= 0),
    energy_decay_seconds INTEGER NOT NULL CHECK(energy_decay_seconds >= 0),
    attention_decay_seconds INTEGER NOT NULL CHECK(attention_decay_seconds >= 0),
    revision INTEGER NOT NULL CHECK(revision >= 0),
    evaluated_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pet_state_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    revision INTEGER NOT NULL CHECK(revision >= 0),
    mutation_kind TEXT NOT NULL,
    previous_state_json TEXT,
    current_state_json TEXT NOT NULL,
    band_transitions_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pet_state_history_created_at
ON pet_state_history(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_pet_state_history_kind
ON pet_state_history(mutation_kind, id DESC);

INSERT INTO schema_version(version,name) VALUES (9,'pet_state');
CREATE TABLE IF NOT EXISTS pet_reward_grants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reward_kind TEXT NOT NULL CHECK(
        reward_kind IN (
            'care_feed',
            'care_rest',
            'care_spend_time',
            'conversation_completed'
        )
    ),
    event_id TEXT,
    xp_awarded INTEGER NOT NULL CHECK(xp_awarded >= 0),
    currency_awarded INTEGER NOT NULL CHECK(currency_awarded >= 0),
    granted_at TEXT NOT NULL,
    CHECK(xp_awarded > 0 OR currency_awarded > 0),
    CHECK(
        (
            reward_kind = 'conversation_completed'
            AND xp_awarded = 1
            AND currency_awarded = 0
        )
        OR
        (
            reward_kind != 'conversation_completed'
            AND xp_awarded = 5
            AND currency_awarded = 2
        )
    ),
    CHECK(
        (reward_kind = 'conversation_completed' AND event_id IS NOT NULL)
        OR
        (reward_kind != 'conversation_completed' AND event_id IS NULL)
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_pet_reward_grants_event
ON pet_reward_grants(event_id)
WHERE event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_pet_reward_grants_kind_time
ON pet_reward_grants(reward_kind, granted_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_pet_reward_grants_time
ON pet_reward_grants(granted_at DESC, id DESC);

INSERT INTO schema_version(version,name) VALUES (10,'pet_rewards');
CREATE TABLE IF NOT EXISTS shop_transactions (
    transaction_id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    catalog_version INTEGER NOT NULL CHECK(catalog_version >= 1),
    price INTEGER NOT NULL CHECK(price >= 0),
    balance_before INTEGER NOT NULL CHECK(balance_before >= 0),
    balance_after INTEGER NOT NULL CHECK(balance_after >= 0),
    purchased_at TEXT NOT NULL,
    CHECK(balance_before - price = balance_after)
);

CREATE INDEX IF NOT EXISTS idx_shop_transactions_time
ON shop_transactions(purchased_at DESC, transaction_id DESC);

CREATE INDEX IF NOT EXISTS idx_shop_transactions_item
ON shop_transactions(item_id, purchased_at DESC);

CREATE TABLE IF NOT EXISTS shop_inventory (
    item_id TEXT PRIMARY KEY,
    acquired_at TEXT NOT NULL,
    acquisition_source TEXT NOT NULL CHECK(
        acquisition_source IN ('starter', 'purchase', 'reward', 'migration')
    ),
    purchase_transaction_id TEXT UNIQUE,
    CHECK(
        (acquisition_source = 'purchase' AND purchase_transaction_id IS NOT NULL)
        OR
        (acquisition_source != 'purchase' AND purchase_transaction_id IS NULL)
    ),
    FOREIGN KEY(purchase_transaction_id)
        REFERENCES shop_transactions(transaction_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_shop_inventory_acquired
ON shop_inventory(acquired_at ASC, item_id ASC);

CREATE TABLE IF NOT EXISTS shop_equipment (
    slot TEXT PRIMARY KEY CHECK(slot IN ('head', 'face', 'neck', 'accessory')),
    item_id TEXT NOT NULL UNIQUE,
    equipped_at TEXT NOT NULL,
    FOREIGN KEY(item_id) REFERENCES shop_inventory(item_id) ON DELETE RESTRICT
);

INSERT INTO schema_version(version,name) VALUES (11,'shop_inventory');
CREATE TABLE IF NOT EXISTS pet_appearance_selection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    appearance_id TEXT NOT NULL CHECK (
        appearance_id IN ('seifuku', 'dress', 'vermillion')
    ),
    selected_at TEXT NOT NULL
);

INSERT OR IGNORE INTO pet_appearance_selection(id, appearance_id, selected_at)
VALUES (1, 'seifuku', '1970-01-01T00:00:00.000000+00:00');

INSERT INTO schema_version(version,name) VALUES (12,'appearance_selection');
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

INSERT INTO schema_version(version,name) VALUES (13,'external_integrations');
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

INSERT INTO schema_version(version,name) VALUES (14,'notification_center');
