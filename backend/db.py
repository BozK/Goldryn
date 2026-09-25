import sqlite3
from collections.abc import Iterator
from pathlib import Path

from fastapi import Request

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
