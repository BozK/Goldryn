import sqlite3
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

from fastapi import Request

import logger

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# SQL expression for "now" in the same format as the schema's created_at defaults.
NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"

# ============================================================================
# Connections
# ============================================================================


def connect(db_path: Path) -> sqlite3.Connection:
    """
    Open a connection with Row results and foreign keys enforced.

    SQLite leaves foreign keys off by default, per connection, so every
    connection has to turn them on for ON DELETE CASCADE to mean anything.
    check_same_thread is off because FastAPI may create the connection in one
    threadpool worker and use it in another; each request still gets its own.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: one connection per request, closed afterwards."""
    conn = connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


# ============================================================================
# Schema versioning
# ============================================================================

# MIGRATIONS[n] takes the database from user_version n to n + 1. Append new
# steps to the end; never edit one that has already shipped.
MIGRATIONS: list[str] = [
    SCHEMA_PATH.read_text(encoding="utf-8"),
]


def init_db(db_path: Path) -> None:
    """Create the database if needed and apply any pending migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for step in range(version, len(MIGRATIONS)):
            # user_version is part of the transaction, so a failed step leaves
            # both the schema and the version number untouched.
            conn.executescript(
                f"BEGIN;\n{MIGRATIONS[step]}\nPRAGMA user_version = {step + 1};\nCOMMIT;"
            )
    finally:
        conn.close()


# ============================================================================
# Logged execution
#
# Every query the helpers below make goes through _select or _write, which
# time it and write one DB log line (logger.py). connect() and init_db() call
# conn.execute directly, so the foreign_keys PRAGMA and migrations aren't logged.
# ============================================================================


def _select(conn: sqlite3.Connection, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
    """Run a SELECT and fetch every row. Rows are fetched here so they can be logged."""
    start = time.perf_counter()
    try:
        rows = conn.execute(sql, params).fetchall()
    except Exception as exc:
        logger.log_db_error(sql, params, exc, (time.perf_counter() - start) * 1000)
        raise
    logger.log_select(sql, params, rows, (time.perf_counter() - start) * 1000)
    return rows


def _select_one(conn: sqlite3.Connection, sql: str, params: Sequence = ()) -> sqlite3.Row | None:
    rows = _select(conn, sql, params)
    return rows[0] if rows else None


def _write(conn: sqlite3.Connection, sql: str, params: Sequence = ()) -> sqlite3.Cursor:
    """Run one INSERT/UPDATE/DELETE and commit it (`with conn:` rolls back if it raises)."""
    start = time.perf_counter()
    try:
        with conn:
            cursor = conn.execute(sql, params)
    except Exception as exc:
        logger.log_db_error(sql, params, exc, (time.perf_counter() - start) * 1000)
        raise
    logger.log_write(sql, params, cursor, (time.perf_counter() - start) * 1000)
    return cursor


# ============================================================================
# Query helpers
#
# Writes commit immediately (via _write). Column names in dynamic SET/INSERT
# clauses come from the *_FIELDS whitelists below, never from the request.
# Children of an archived item are treated as missing: every note/record query
# joins through ACTIVE_ITEM_IDS.
# ============================================================================

ITEM_FIELDS = ("name", "color", "cadence_days", "next_maintenance_notes")
NOTE_FIELDS = ("body",)
RECORD_FIELDS = ("date", "summary", "cost", "contractor_info")

ACTIVE_ITEM_IDS = "SELECT id FROM items WHERE archived_at IS NULL"


def _columns(fields: dict, allowed: tuple[str, ...]) -> list[str]:
    unknown = set(fields) - set(allowed)
    if unknown:
        raise ValueError(f"Unknown column(s): {sorted(unknown)}")
    return list(fields)


def _update(conn: sqlite3.Connection, table: str, allowed: tuple[str, ...], row_id: int, fields: dict) -> bool:
    """UPDATE one active row. Returns False if it doesn't exist (or its item is archived)."""
    columns = _columns(fields, allowed)
    owner = "archived_at IS NULL" if table == "items" else f"item_id IN ({ACTIVE_ITEM_IDS})"
    if not columns:
        return _select_one(conn, f"SELECT 1 FROM {table} WHERE id = ? AND {owner}", (row_id,)) is not None
    assignments = ", ".join(f"{column} = ?" for column in columns)
    cursor = _write(
        conn,
        f"UPDATE {table} SET {assignments} WHERE id = ? AND {owner}",
        (*fields.values(), row_id),
    )
    return cursor.rowcount == 1


def _insert_child(conn: sqlite3.Connection, table: str, allowed: tuple[str, ...], item_id: int, fields: dict) -> int | None:
    """INSERT a note/record under an active item. Returns the new id, or None if the item is missing or archived."""
    columns = _columns(fields, allowed)
    placeholders = ", ".join("?" for _ in columns)
    # INSERT ... SELECT inserts nothing when the item isn't active: one statement, no race.
    cursor = _write(
        conn,
        f"INSERT INTO {table} (item_id, {', '.join(columns)}) "
        f"SELECT id, {placeholders} FROM items WHERE id = ? AND archived_at IS NULL",
        (*fields.values(), item_id),
    )
    return cursor.lastrowid if cursor.rowcount == 1 else None


def _delete_child(conn: sqlite3.Connection, table: str, row_id: int) -> bool:
    cursor = _write(
        conn,
        f"DELETE FROM {table} WHERE id = ? AND item_id IN ({ACTIVE_ITEM_IDS})",
        (row_id,),
    )
    return cursor.rowcount == 1


# -------- Items --------

_ITEM_SELECT = """
    SELECT i.id, i.name, i.color, i.cadence_days, i.next_maintenance_notes, i.created_at,
           MAX(m.date) AS last_maintenance_date
    FROM items i
    LEFT JOIN maintenance_records m ON m.item_id = i.id
    WHERE i.archived_at IS NULL
"""


def list_items(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Active items, oldest first. LEFT JOIN keeps items that have no records yet."""
    return _select(conn, _ITEM_SELECT + " GROUP BY i.id ORDER BY i.created_at, i.id")


def get_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return _select_one(conn, _ITEM_SELECT + " AND i.id = ? GROUP BY i.id", (item_id,))


def insert_item(conn: sqlite3.Connection, fields: dict) -> int:
    columns = _columns(fields, ITEM_FIELDS)
    placeholders = ", ".join("?" for _ in columns)
    cursor = _write(
        conn,
        f"INSERT INTO items ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(fields.values()),
    )
    return cursor.lastrowid


def update_item(conn: sqlite3.Connection, item_id: int, fields: dict) -> bool:
    return _update(conn, "items", ITEM_FIELDS, item_id, fields)


def archive_item(conn: sqlite3.Connection, item_id: int) -> bool:
    """Soft delete. Notes and records stay in the DB but become unreachable."""
    cursor = _write(
        conn,
        f"UPDATE items SET archived_at = {NOW_SQL} WHERE id = ? AND archived_at IS NULL",
        (item_id,),
    )
    return cursor.rowcount == 1


# -------- Notes --------


def list_notes(conn: sqlite3.Connection, item_id: int) -> list[sqlite3.Row]:
    return _select(
        conn,
        "SELECT id, body, created_at FROM notes WHERE item_id = ? ORDER BY created_at DESC, id DESC",
        (item_id,),
    )


def get_note(conn: sqlite3.Connection, note_id: int) -> sqlite3.Row | None:
    return _select_one(
        conn,
        f"SELECT id, body, created_at FROM notes WHERE id = ? AND item_id IN ({ACTIVE_ITEM_IDS})",
        (note_id,),
    )


def insert_note(conn: sqlite3.Connection, item_id: int, fields: dict) -> int | None:
    return _insert_child(conn, "notes", NOTE_FIELDS, item_id, fields)


def update_note(conn: sqlite3.Connection, note_id: int, fields: dict) -> bool:
    return _update(conn, "notes", NOTE_FIELDS, note_id, fields)


def delete_note(conn: sqlite3.Connection, note_id: int) -> bool:
    return _delete_child(conn, "notes", note_id)


# -------- Maintenance records --------

_RECORD_COLUMNS = "id, date, summary, cost, contractor_info"


def list_records(conn: sqlite3.Connection, item_id: int) -> list[sqlite3.Row]:
    return _select(
        conn,
        f"SELECT {_RECORD_COLUMNS} FROM maintenance_records WHERE item_id = ? ORDER BY date DESC, id DESC",
        (item_id,),
    )


def get_record(conn: sqlite3.Connection, record_id: int) -> sqlite3.Row | None:
    return _select_one(
        conn,
        f"SELECT {_RECORD_COLUMNS} FROM maintenance_records WHERE id = ? AND item_id IN ({ACTIVE_ITEM_IDS})",
        (record_id,),
    )


def insert_record(conn: sqlite3.Connection, item_id: int, fields: dict) -> int | None:
    return _insert_child(conn, "maintenance_records", RECORD_FIELDS, item_id, fields)


def update_record(conn: sqlite3.Connection, record_id: int, fields: dict) -> bool:
    return _update(conn, "maintenance_records", RECORD_FIELDS, record_id, fields)


def delete_record(conn: sqlite3.Connection, record_id: int) -> bool:
    return _delete_child(conn, "maintenance_records", record_id)
