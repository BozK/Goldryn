# Goldryn — DB Design

**Engine:** SQLite

The schema below lives in `backend/schema.sql` and is applied by `init_db()` in `backend/db.py`.

## Schema

```sql
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
```

## Design notes

- **SQLite over NoSQL:** The data is relational, not document-shaped. Tags are shared/referenced across items (explicitly many-to-many), and there's a real need for cross-cutting queries (e.g. "all records over $X this year") that cut across the item hierarchy rather than down it. SQLite's joins and FK constraints handle this cleanly; a document store would mean either duplicating data or reimplementing joins in application code. Read-heavy, fixed-schema, low write volume — none of the conditions that favor NoSQL apply here.

- **Contractors are intentionally denormalized** (`contractor_info` as freeform text on `maintenance_records`, no separate table). Normalizing would require UI/API for contractor lookup and creation (autocomplete, dedicated add-contractor flow) that isn't worth it at single-user scale, especially since contractors tend to be specialty-specific and less reused than initially assumed. Tradeoff accepted: possible inconsistent naming across records (e.g. "Bob's HVAC" vs "Bob HVAC LLC") — acceptable risk at this scale and user count.

- **NextMaintenance is derived, not stored.** Computed at read time as `most_recent_maintenance_record.date + item.cadence_days`. Storing it separately would create a second source of truth that can drift from the underlying records.

- **Cadence** is a plain integer (`cadence_days`) rather than a structured value/unit — sufficient precision for this use case without added conversion logic.

- **Anticipatory maintenance info** lives as a nullable column directly on `items` (`next_maintenance_notes`) rather than a separate object — no separate Date/Contractor/Cost needed since the date is derived and cost/contractor aren't known ahead of time in most cases. If multiple upcoming projections per item are ever needed, this is the signal to graduate it into its own table — not before.

- **Multiple notes per item** are supported natively via the `notes.item_id` FK — no schema change needed for freeform forward-looking notes.

- **Tags table is separate** from a free-text field specifically to support autocomplete suggestions when creating new items.

- **Items use soft delete via `archived_at`** (nullable timestamp, NULL = active). Deleting an item ("removing" it from the UI) sets `archived_at` to the current timestamp (same format as `created_at`) instead of a hard `DELETE`, so notes and maintenance history survive a delete-then-regret (e.g. sold the water filter, replaced the whole unit). Default item list queries should filter `WHERE archived_at IS NULL`; a hard-delete/purge path can be added later if you actually want one. `ON DELETE CASCADE` on child tables still applies if an item row is ever truly purged.

- **Foreign keys are enabled per connection.** SQLite ships with FK enforcement off, and the setting doesn't persist in the file. `db.connect()` runs `PRAGMA foreign_keys = ON` on every connection; without it, `REFERENCES` and `ON DELETE CASCADE` are silently ignored.

- **Schema versioning uses `PRAGMA user_version`.** `init_db()` runs at app startup and compares the file's `user_version` with the `MIGRATIONS` list in `db.py`. A fresh file (version 0) gets `schema.sql` and becomes version 1. A later schema change is appended as a new migration step and never edits an earlier one. Each step runs in one transaction together with its version bump, so a failed migration leaves the file unchanged. No migration framework: at one user and a handful of tables it's a list of SQL strings.

## Open considerations

- **Timestamps as TEXT.** SQLite has no native datetime type, so timestamps are `TEXT` in ISO-8601 UTC with a `Z` suffix (`2026-01-04T12:00:00Z`), which sorts and compares correctly as a string. The defaults use `strftime('%Y-%m-%dT%H:%M:%SZ', 'now')` rather than `datetime('now')`: the latter emits `2026-01-04 12:00:00`, which JavaScript's `Date` parses as *local* time. Dates without a time (`maintenance_records.date`) are plain `YYYY-MM-DD`.
- **Auth/session storage is going to be simple.** Phase 1 includes a login page but there's no need for a full on users table. This app will have 1 login; the username and password will be stored at the environment variable level in Prod.
- **Indexes.** Not urgent at this scale, but once you're querying "next maintenance due," you'll want an index on `maintenance_records(item_id, date)` for the derived NextMaintenance lookup, and on `item_tags(tag_id)` for tag-based search in phase 3. Fine to defer until you actually feel a slowdown — just flagging it exists as a lever.
