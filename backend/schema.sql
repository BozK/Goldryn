-- Goldryn schema, version 1. See DB_DESIGN.md.
-- Timestamps are ISO-8601 UTC ("2026-01-04T12:00:00Z"); dates are "YYYY-MM-DD".

CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    color TEXT,
    cadence_days INTEGER,              -- nullable; days between recurring maintenance
    next_maintenance_notes TEXT,       -- nullable; freeform notes on the upcoming event
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    archived_at TEXT                   -- nullable; soft delete marker, NULL = active
);

CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE maintenance_records (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    summary TEXT,
    cost REAL,
    contractor_info TEXT   -- freeform: name, phone, email, website, whatever's on hand
);

CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE item_tags (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);
