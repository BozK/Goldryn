import json
import logging
import re
import sqlite3
import threading
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

import db
from GoldrynBackend import create_app
from logger import LOGGER_NAME, DailyFileHandler, redact
from settings import DEFAULT_LOG_DIR, load_settings

from conftest import PASSWORD, USERNAME

LOCAL_TIME = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
DURATION = re.compile(r"^\d+\.\dms$")
IP = "203.0.113.7"


def read_lines(settings) -> list[str]:
    files = list(settings.log_dir.glob("*.log"))
    if not files:
        return []
    assert [f.name for f in files] == [f"Goldryn-{date.today().isoformat()}.log"]
    return files[0].read_text(encoding="utf-8").splitlines()


def fields(line: str) -> list[str]:
    return line.split(" | ")


def api_lines(settings) -> list[list[str]]:
    return [fields(line) for line in read_lines(settings) if fields(line)[1] == "API"]


def db_lines(settings) -> list[list[str]]:
    return [fields(line) for line in read_lines(settings) if fields(line)[1] == "DB"]


def api_line(settings, target: str) -> list[str]:
    """The last API line for e.g. "PATCH /api/items/1"."""
    return [f for f in api_lines(settings) if f[3] == target][-1]


def db_line(settings, sql_start: str) -> list[str]:
    """The last DB line whose "table: SQL" field starts with sql_start."""
    return [f for f in db_lines(settings) if f[3].startswith(sql_start)][-1]


def create_item(client, **fields):
    res = client.post("/api/items", json={"name": "Water filter", **fields})
    assert res.status_code == 201, res.text
    return res.json()


# ============================================================================
# Line format
# ============================================================================


def test_api_line_fields_in_order(client, settings):
    item = create_item(client)
    res = client.patch(f"/api/items/{item['id']}", json={"cadence_days": 90})

    line = api_line(settings, f"PATCH /api/items/{item['id']}")
    assert len(line) == 7  # no IP field without CF-Connecting-IP
    timestamp, kind, outcome, target, request, response, duration = line
    assert LOCAL_TIME.match(timestamp)
    # Local time, not UTC.
    assert abs((datetime.now() - datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")).total_seconds()) < 60
    assert (kind, outcome, target) == ("API", "200", f"PATCH /api/items/{item['id']}")
    assert json.loads(request) == {"cadence_days": 90}
    assert json.loads(response) == res.json()
    assert DURATION.match(duration)


def test_db_write_line_fields_in_order(client, settings):
    item = create_item(client)
    client.patch(f"/api/items/{item['id']}", json={"cadence_days": 90})

    timestamp, kind, outcome, target, params, result, duration = db_line(settings, "items: UPDATE")
    assert LOCAL_TIME.match(timestamp)
    assert (kind, outcome) == ("DB", "OK")
    assert target == "items: UPDATE items SET cadence_days = ? WHERE id = ? AND archived_at IS NULL"
    assert json.loads(params) == [90, item["id"]]
    assert result == "rowcount=1"
    assert DURATION.match(duration)

    insert = db_line(settings, "items: INSERT")
    assert insert[5] == f"rowcount=1, lastrowid={item['id']}"


def test_db_select_line_has_rows_and_collapsed_sql(client, settings):
    item = create_item(client, cadence_days=30)
    client.get(f"/api/items/{item['id']}")

    # The multi-line _ITEM_SELECT, whitespace collapsed; the JOIN is logged under its primary table.
    line = db_line(settings, "items: SELECT i.id, i.name")
    assert "\n" not in line[3] and "  " not in line[3]
    assert "LEFT JOIN maintenance_records m ON m.item_id = i.id" in line[3]
    assert json.loads(line[4]) == [item["id"]]
    rows = json.loads(line[5])
    assert rows[0]["name"] == "Water filter" and rows[0]["cadence_days"] == 30

    # Child queries with a subselect on items are logged under the child table.
    notes = db_line(settings, "notes: SELECT id, body, created_at FROM notes WHERE item_id = ?")
    assert (notes[2], notes[5]) == ("OK", "[]")


def test_db_lines_precede_their_api_line(client, settings):
    create_item(client)
    kinds = [fields(line)[1] for line in read_lines(settings)]
    # login (API), INSERT + SELECT (DB), POST (API)
    assert kinds[-3:] == ["DB", "DB", "API"]


def test_init_db_and_pragmas_are_not_logged(client, settings):
    create_item(client)
    text = "\n".join(read_lines(settings))
    assert "PRAGMA" not in text
    assert "CREATE TABLE" not in text


# ============================================================================
# Secrets
# ============================================================================


def test_login_password_is_redacted(anon, settings):
    anon.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD}).raise_for_status()
    anon.post("/api/auth/login", json={"username": USERNAME, "password": "wrong-guess"})

    ok, bad = [f for f in api_lines(settings) if f[3] == "POST /api/auth/login"]
    assert json.loads(ok[4]) == {"username": USERNAME, "password": "***"}
    assert ok[2] == "200"
    assert json.loads(bad[4]) == {"username": USERNAME, "password": "***"}
    assert bad[2] == "400"
    text = "\n".join(read_lines(settings))
    assert PASSWORD not in text
    assert "wrong-guess" not in text


def test_password_in_422_detail_is_redacted(anon, settings):
    """FastAPI echoes the offending body back as "input" in its 422 detail."""
    anon.post("/api/auth/login", json={"password": "only-a-password"})
    anon.post("/api/auth/login", json={"username": USERNAME, "password": 13371337})

    text = "\n".join(read_lines(settings))
    assert "only-a-password" not in text
    assert "13371337" not in text
    assert all(f[2] == "422" for f in api_lines(settings))


def test_redact_reaches_any_depth():
    body = {"a": [{"Password": "x", "b": {"password": {"nested": 1}}}], "password": None, "keep": "password"}
    assert redact(body) == {"a": [{"Password": "***", "b": {"password": "***"}}], "password": "***", "keep": "password"}


def test_no_cookie_or_session_id_logged(client, settings):
    session_id = client.cookies["session_id"]
    client.get("/api/items")
    client.post("/api/auth/logout")

    text = "\n".join(read_lines(settings))
    assert session_id not in text
    assert "session_id" not in text
    assert "cookie" not in text.lower()


# ============================================================================
# Truncation
# ============================================================================


def test_body_fields_truncated_to_200_chars(client, settings):
    item = create_item(client)
    body = "x" * 500
    client.post(f"/api/items/{item['id']}/notes", json={"body": body})

    request_json = json.dumps({"body": body})
    request_field = api_line(settings, f"POST /api/items/{item['id']}/notes")[4]
    assert request_field == f"{request_json[:200]}…(+{len(request_json) - 200} chars)"

    insert = db_line(settings, "notes: INSERT")
    params_json = json.dumps([body, item["id"]])
    assert insert[4] == f"{params_json[:200]}…(+{len(params_json) - 200} chars)"

    select = db_line(settings, "notes: SELECT")
    assert re.search(r"…\(\+\d+ chars\)$", select[5])


# ============================================================================
# Client IP
# ============================================================================


def test_ip_comes_from_cf_connecting_ip(client, settings):
    client.get("/api/items", headers={"CF-Connecting-IP": IP})

    api = api_line(settings, "GET /api/items")
    assert api[-1] == f"IP: {IP}"
    # DB lines carry the IP of the request that made them.
    assert db_line(settings, "items: SELECT")[-1] == f"IP: {IP}"


def test_no_ip_field_without_the_header(client, settings):
    # Only CF-Connecting-IP counts: no X-Forwarded-For, no socket address ("testclient" here).
    client.get("/api/items", headers={"X-Forwarded-For": IP})

    assert len(api_line(settings, "GET /api/items")) == 7
    assert len(db_line(settings, "items: SELECT")) == 7
    text = "\n".join(read_lines(settings))
    assert "IP:" not in text
    assert IP not in text
    assert "testclient" not in text


def test_ip_does_not_leak_into_the_next_request(client, settings):
    client.get("/api/items", headers={"CF-Connecting-IP": IP})
    client.get("/api/me")
    assert len(api_line(settings, "GET /api/me")) == 7


# ============================================================================
# Scope and status codes
# ============================================================================


def test_non_api_paths_not_logged(anon, settings):
    anon.get("/health")
    anon.get("/")
    anon.get("/index.html")
    anon.get("/apiary")
    assert read_lines(settings) == []


def test_error_statuses_logged(client, settings):
    client.post("/api/items", json={})
    client.get("/api/items/999")

    invalid = api_line(settings, "POST /api/items")
    assert (invalid[2], json.loads(invalid[4])) == ("422", {})
    assert json.loads(invalid[5])["detail"][0]["loc"] == ["body", "name"]

    missing = api_line(settings, "GET /api/items/999")
    assert (missing[2], missing[4], json.loads(missing[5])) == ("404", "-", {"detail": "Item not found"})


def test_401_logs_the_unread_body(anon, settings):
    """The route rejects before parsing the body, but the middleware still logs it."""
    anon.post("/api/items", json={"name": "Gutters"})
    line = api_line(settings, "POST /api/items")
    assert (line[2], json.loads(line[4])) == ("401", {"name": "Gutters"})


def test_non_json_body_is_not_logged_raw(anon, settings):
    anon.post("/api/auth/login", content=b'password=hunter2', headers={"Content-Type": "text/plain"})
    line = api_line(settings, "POST /api/auth/login")
    assert line[4] == "<16 bytes, not JSON>"
    assert "hunter2" not in "\n".join(read_lines(settings))


def test_response_reaches_client_intact(client):
    """Copying the response body for the log mustn't eat any of it."""
    item = create_item(client, next_maintenance_notes="n" * 5000)
    res = client.get(f"/api/items/{item['id']}")
    assert res.json()["next_maintenance_notes"] == "n" * 5000


# ============================================================================
# DB errors
# ============================================================================


def test_db_error_logged_and_raised(client, settings):
    item = create_item(client)
    conn = db.connect(settings.db_path)
    conn.execute("DROP TABLE notes")
    conn.close()

    with pytest.raises(sqlite3.OperationalError, match="no such table: notes"):
        client.get(f"/api/items/{item['id']}")

    failed = db_line(settings, "notes: SELECT")
    assert failed[2] == "ERROR OperationalError: no such table: notes"
    assert failed[5] == "-"
    assert api_line(settings, f"GET /api/items/{item['id']}")[2] == "500"


def test_write_error_logged_and_raised(app, settings):
    conn = db.connect(settings.db_path)
    with pytest.raises(sqlite3.IntegrityError):
        db._write(conn, "INSERT INTO notes (item_id, body) VALUES (?, ?)", (999, "orphan"))
    conn.close()

    line = db_line(settings, "notes: INSERT")
    assert line[2] == "ERROR IntegrityError: FOREIGN KEY constraint failed"
    assert json.loads(line[4]) == [999, "orphan"]


# ============================================================================
# Files and setup
# ============================================================================


def record(message: str) -> logging.LogRecord:
    return logging.LogRecord(LOGGER_NAME, logging.INFO, __file__, 0, message, None, None)


def test_daily_file_rolls_over_at_midnight(tmp_path):
    today = [date(2026, 9, 25)]
    handler = DailyFileHandler(tmp_path, clock=lambda: today[0])
    handler.handle(record("before midnight"))
    today[0] = date(2026, 9, 26)
    handler.handle(record("after midnight"))
    handler.close()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["Goldryn-2026-09-25.log", "Goldryn-2026-09-26.log"]
    assert (tmp_path / "Goldryn-2026-09-25.log").read_text(encoding="utf-8") == "before midnight\n"
    assert (tmp_path / "Goldryn-2026-09-26.log").read_text(encoding="utf-8") == "after midnight\n"


def test_daily_file_appends_after_restart(tmp_path):
    for message in ("first run", "second run"):
        handler = DailyFileHandler(tmp_path, clock=lambda: date(2026, 9, 25))
        handler.handle(record(message))
        handler.close()
    assert (tmp_path / "Goldryn-2026-09-25.log").read_text(encoding="utf-8") == "first run\nsecond run\n"


def test_daily_file_rollover_is_thread_safe(tmp_path):
    """Threads emitting across midnight: every line lands whole, in one of the two files."""
    today = [date(2026, 9, 25)]
    handler = DailyFileHandler(tmp_path, clock=lambda: today[0])

    def worker(n):
        for i in range(200):
            if n == 0 and i == 100:
                today[0] = date(2026, 9, 26)
            handler.handle(record(f"thread {n} line {i}"))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    handler.close()

    lines = [line for p in tmp_path.iterdir() for line in p.read_text(encoding="utf-8").splitlines()]
    assert sorted(lines) == sorted(f"thread {n} line {i}" for n in range(4) for i in range(200))


def test_no_file_until_something_is_logged(settings, app):
    assert not settings.log_dir.exists() or list(settings.log_dir.iterdir()) == []


def test_repeated_create_app_does_not_stack_handlers(settings):
    for _ in range(3):
        app = create_app(settings)
    assert len(logging.getLogger(LOGGER_NAME).handlers) == 2  # today's file + stderr

    TestClient(app).get("/api/me")
    assert len([f for f in api_lines(settings) if f[3] == "GET /api/me"]) == 1


def test_lines_echo_to_stderr(anon, capsys):
    anon.get("/api/me")
    assert "| API | 401 | GET /api/me |" in capsys.readouterr().err


def test_load_settings_log_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("GOLDRYN_USERNAME", USERNAME)
    monkeypatch.setenv("GOLDRYN_PASSWORD_HASH", "$2b$04$hash")
    monkeypatch.delenv("GOLDRYN_LOG_DIR", raising=False)
    assert load_settings().log_dir == DEFAULT_LOG_DIR

    monkeypatch.setenv("GOLDRYN_LOG_DIR", str(tmp_path / "elsewhere"))
    assert load_settings().log_dir == tmp_path / "elsewhere"
