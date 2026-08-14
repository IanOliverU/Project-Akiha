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
