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
