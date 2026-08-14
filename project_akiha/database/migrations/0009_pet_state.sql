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
