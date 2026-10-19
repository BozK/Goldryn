import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections.abc import Callable, Sequence
from contextvars import ContextVar
from datetime import date
from pathlib import Path

# One line per /api request and per DB query a route makes:
#
#   2026-09-25 14:03:07 | API | 200 | PATCH /api/items/3 | {"name": "Filter"} | {"id": 3, ...} | 12.4ms | IP: 203.0.113.7
#   2026-09-25 14:03:07 | DB | OK | items: UPDATE items SET name = ? WHERE ... | ["Filter", 3] | rowcount=1 | 0.3ms | IP: 203.0.113.7
#
# The IP field is only there when the request carried CF-Connecting-IP.

LOGGER_NAME = "goldryn"
FILE_PREFIX = "Goldryn"
SEP = " | "
EMPTY = "-"
MAX_FIELD_CHARS = 200
REDACTED = "***"
# Cloudflare's header for the real client. The socket peer is always Cloudflare
# or the local tunnel, so it's never used as a fallback.
IP_HEADER = b"cf-connecting-ip"

log = logging.getLogger(LOGGER_NAME)

# The client IP of the request being served, so DB lines can carry it too.
# Set by RequestLogMiddleware; None outside a request or without the header.
client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)

# ============================================================================
# Field formatting
# ============================================================================

_WHITESPACE = re.compile(r"\s+")
_TABLE = re.compile(r"\b(?:FROM|INTO|UPDATE)\s+(\w+)", re.IGNORECASE)


def one_line(text: str) -> str:
    """Collapse all whitespace (newlines included) to single spaces, so a field can't break the line."""
    return _WHITESPACE.sub(" ", text).strip()


def truncate(text: str, limit: int = MAX_FIELD_CHARS) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}…(+{len(text) - limit} chars)"


def _is_password(key: object) -> bool:
    return isinstance(key, str) and key.lower() == "password"


def redact(value: object) -> object:
    """
    A copy of a JSON value with every "password" key's value replaced by "***", at any depth.

    Also covers FastAPI's 422 detail, which echoes a bad field's value as "input"
    next to its "loc" (e.g. {"loc": ["body", "password"], "input": ...}), and
    echoes a body that isn't a JSON object as a raw string at "loc": ["body"].
    Request bodies that aren't JSON are never logged, so neither is that echo.
    """
    if isinstance(value, dict):
        out = {key: REDACTED if _is_password(key) else redact(item) for key, item in value.items()}
        loc = value.get("loc")
        if "input" in out and isinstance(loc, list) and loc:
            if _is_password(loc[-1]) or (loc == ["body"] and isinstance(out["input"], str)):
                out["input"] = REDACTED
        return out
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _json(value: object) -> str:
    # json.dumps escapes newlines inside strings, so the result is always one line.
    return json.dumps(value, ensure_ascii=False, default=str)


def _field(text: str) -> str:
    return truncate(text) if text else EMPTY


def body_field(raw: bytes) -> str:
    """A request/response body: redacted JSON, or a size note if it isn't JSON (never the raw bytes)."""
    if not raw:
        return EMPTY
    try:
        value = json.loads(raw)
    except ValueError:  # includes UnicodeDecodeError
        return f"<{len(raw)} bytes, not JSON>"
    return _field(_json(redact(value)))


def table_of(sql: str) -> str:
    """The first FROM/INTO/UPDATE target, i.e. the primary table (a JOIN or subselect comes later)."""
    match = _TABLE.search(sql)
    return match.group(1) if match else EMPTY


def _emit(kind: str, outcome: str, target: str, request: str, response: str, ms: float) -> None:
    fields = [kind, outcome, target, request, response, f"{ms:.1f}ms"]
    ip = client_ip.get()
    if ip:
        fields.append(f"IP: {ip}")
    log.info(SEP.join(fields))


# ============================================================================
# DB lines
#
# Called from db._select / db._write, the only two places helpers execute SQL.
# ============================================================================


def _params_field(params: Sequence) -> str:
    return _field(_json(list(params))) if params else EMPTY


def _row(row: object) -> object:
    return dict(row) if isinstance(row, sqlite3.Row) else row


def log_select(sql: str, params: Sequence, rows: list, ms: float) -> None:
    if log.isEnabledFor(logging.INFO):
        rows_field = _field(_json([_row(row) for row in rows]))
        _emit("DB", "OK", f"{table_of(sql)}: {one_line(sql)}", _params_field(params), rows_field, ms)


def log_write(sql: str, params: Sequence, cursor: sqlite3.Cursor, ms: float) -> None:
    if log.isEnabledFor(logging.INFO):
        result = f"rowcount={cursor.rowcount}"
        # lastrowid is only meaningful after an INSERT that actually inserted something.
        if sql.lstrip().upper().startswith("INSERT") and cursor.rowcount > 0:
            result += f", lastrowid={cursor.lastrowid}"
        _emit("DB", "OK", f"{table_of(sql)}: {one_line(sql)}", _params_field(params), result, ms)


def log_db_error(sql: str, params: Sequence, error: BaseException, ms: float) -> None:
    if log.isEnabledFor(logging.INFO):
        outcome = one_line(f"ERROR {type(error).__name__}: {error}")
        _emit("DB", outcome, f"{table_of(sql)}: {one_line(sql)}", _params_field(params), EMPTY, ms)


# ============================================================================
# API lines
# ============================================================================


def _is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


class RequestLogMiddleware:
    """
    Pure ASGI middleware: one API line per /api/* request. Everything else
    (/health, the static frontend) passes straight through unlogged.

    The request body is read up front and replayed to the app, so it's logged
    even when the route never reads it (a 401 is decided before the body is
    parsed). Response body chunks are copied as they go by; the client gets
    them unchanged.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not _is_api(scope["path"]):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        ip = one_line(dict(scope["headers"]).get(IP_HEADER, b"").decode("latin-1"))
        token = client_ip.set(ip or None)

        chunks: list[bytes] = []
        pending: list[dict] = []
        while True:
            message = await receive()
            if message["type"] != "http.request":  # e.g. http.disconnect: hand it on after the body
                pending.append(message)
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        request_body = b"".join(chunks)
        pending.insert(0, {"type": "http.request", "body": request_body, "more_body": False})

        async def replay():
            return pending.pop(0) if pending else await receive()

        # If the app raises before responding, ServerErrorMiddleware (outside us) sends a 500.
        status = 500
        response_chunks: list[bytes] = []

        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            elif message["type"] == "http.response.body":
                response_chunks.append(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, replay, capture)
        finally:
            if log.isEnabledFor(logging.INFO):
                _emit(
                    "API",
                    str(status),
                    one_line(f"{scope['method']} {scope['path']}"),
                    body_field(request_body),
                    body_field(b"".join(response_chunks)),
                    (time.perf_counter() - start) * 1000,
                )
            client_ip.reset(token)


# ============================================================================
# Handlers and setup
# ============================================================================


class DailyFileHandler(logging.FileHandler):
    """
    Appends to <log_dir>/Goldryn-YYYY-MM-DD.log, moving to a new file at local midnight.

    Nothing is ever renamed or deleted (unlike TimedRotatingFileHandler, whose
    rename at rollover is fragile on Windows): each emit checks the date and, if
    it changed, closes the current file and opens the new day's in append mode.
    The clock is injectable so rollover can be tested.
    """

    def __init__(self, log_dir: Path, clock: Callable[[], date] = date.today):
        self._log_dir = Path(log_dir)
        self._clock = clock
        self._day = clock()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        # delay: the file is only created once there's a line to write.
        super().__init__(self._path_for(self._day), mode="a", encoding="utf-8", delay=True)

    def _path_for(self, day: date) -> Path:
        return self._log_dir / f"{FILE_PREFIX}-{day.isoformat()}.log"

    def emit(self, record: logging.LogRecord) -> None:
        # Emits come from threadpool workers. handle() already holds this lock
        # (an RLock), but taking it here keeps the date check and file swap
        # atomic even if emit() is called directly.
        with self.lock:
            today = self._clock()
            if today != self._day:
                self._day = today
                if self.stream is not None:
                    self.stream.close()
                    self.stream = None  # FileHandler.emit reopens it at the new baseFilename
                self.baseFilename = os.path.abspath(self._path_for(today))
            super().emit(record)


class _StderrHandler(logging.StreamHandler):
    """
    Echoes to whatever sys.stderr is at emit time (pytest swaps it per test),
    and escapes characters the console's encoding can't show instead of failing.
    """

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, value):
        pass

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        encoding = getattr(sys.stderr, "encoding", None) or "utf-8"
        return text.encode(encoding, "backslashreplace").decode(encoding)


def configure_logging(log_dir: Path) -> None:
    """
    Send the goldryn logger to today's file in log_dir and to stderr.

    Called by create_app(), so tests and the real server log the same way. Safe
    to call repeatedly: it replaces the handlers it added last time instead of
    stacking more.
    """
    formatter = logging.Formatter(f"%(asctime)s{SEP}%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    for handler in list(log.handlers):
        log.removeHandler(handler)
        handler.close()
    for handler in (DailyFileHandler(log_dir), _StderrHandler()):
        handler.setFormatter(formatter)
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    # The lines are complete as they are; don't also pass them to root/uvicorn handlers.
    log.propagate = False
