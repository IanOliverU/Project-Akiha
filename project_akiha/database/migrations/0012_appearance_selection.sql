CREATE TABLE IF NOT EXISTS pet_appearance_selection (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    appearance_id TEXT NOT NULL CHECK (
        appearance_id IN ('seifuku', 'dress', 'vermillion')
    ),
    selected_at TEXT NOT NULL
);

INSERT OR IGNORE INTO pet_appearance_selection(id, appearance_id, selected_at)
VALUES (1, 'seifuku', '1970-01-01T00:00:00.000000+00:00');
