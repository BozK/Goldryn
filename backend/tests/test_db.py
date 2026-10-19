import re
import sqlite3

import pytest

from db import MIGRATIONS, connect, init_db, insert_item, transaction

TIMESTAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "nested" / "goldryn.db"
    init_db(path)
    return path


def test_init_db_creates_schema_and_sets_version(db_path):
    conn = connect(db_path)
    tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert tables == {"items", "notes", "maintenance_records", "tags", "item_tags"}
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_init_db_is_idempotent(db_path):
    conn = connect(db_path)
    conn.execute("INSERT INTO items (name) VALUES ('Water filter')")
    conn.commit()
    conn.close()

    init_db(db_path)  # must not re-run the schema or wipe data

    assert connect(db_path).execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_foreign_keys_enforced(db_path):
    conn = connect(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO notes (item_id, body) VALUES (999, 'orphan')")


def test_hard_delete_cascades(db_path):
    conn = connect(db_path)
    item_id = conn.execute("INSERT INTO items (name) VALUES ('Furnace')").lastrowid
    conn.execute("INSERT INTO notes (item_id, body) VALUES (?, 'n')", (item_id,))
    conn.execute("INSERT INTO maintenance_records (item_id, date) VALUES (?, '2026-01-01')", (item_id,))
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM maintenance_records").fetchone()[0] == 0


def test_created_at_defaults_are_iso_utc(db_path):
    conn = connect(db_path)
    item_id = conn.execute("INSERT INTO items (name) VALUES ('Gutters')").lastrowid
    conn.execute("INSERT INTO notes (item_id, body) VALUES (?, 'n')", (item_id,))
    assert TIMESTAMP.match(conn.execute("SELECT created_at FROM items").fetchone()[0])
    assert TIMESTAMP.match(conn.execute("SELECT created_at FROM notes").fetchone()[0])


def test_rows_are_addressable_by_name(db_path):
    conn = connect(db_path)
    conn.execute("INSERT INTO items (name, cadence_days) VALUES ('Filter', 90)")
    row = conn.execute("SELECT name, cadence_days FROM items").fetchone()
    assert (row["name"], row["cadence_days"]) == ("Filter", 90)


def test_transaction_commits_helper_writes_together(db_path):
    conn = connect(db_path)
    with transaction(conn):
        insert_item(conn, {"name": "Furnace"})
        insert_item(conn, {"name": "Gutters"})
    assert connect(db_path).execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_transaction_rolls_back_every_write_on_error(db_path):
    conn = connect(db_path)
    with pytest.raises(RuntimeError):
        with transaction(conn):
            insert_item(conn, {"name": "Furnace"})
            raise RuntimeError("boom")
    assert connect(db_path).execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0
