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
