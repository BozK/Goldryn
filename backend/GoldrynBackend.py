import sqlite3
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Path, Request, Response, status
from fastapi.staticfiles import StaticFiles

import db
from auth import SESSION_COOKIE, SESSION_TTL, SessionStore, check_credentials, get_current_user
from GoldrynModels import (
    Item,
    ItemCreate,
    ItemDetail,
    ItemPatch,
    ItemSummary,
    LoginRequest,
    MaintenanceRecord,
    MaintenanceRecordCreate,
    MaintenanceRecordPatch,
    Me,
    MessageResponse,
    Note,
    NoteCreate,
    NotePatch,
    TagSummary,
)
from logger import RequestLogMiddleware, configure_logging
from settings import REPO_ROOT, Settings, load_settings

FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"

CurrentUser = Annotated[str, Depends(get_current_user)]
Conn = Annotated[sqlite3.Connection, Depends(db.get_db)]
# Path ids are bounded to SQLite's integer range; anything larger can't exist and would overflow the driver.
Id = Annotated[int, Path(ge=1, le=2**63 - 1)]

# ============================================================================
# Auth routes
# ============================================================================

auth_router = APIRouter(prefix="/api")


@auth_router.post("/auth/login", response_model=Me)
def login(credentials: LoginRequest, request: Request, response: Response):
    settings: Settings = request.app.state.settings
    if not check_credentials(settings, credentials.username, credentials.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid username or password")

    session_id = request.app.state.sessions.create(settings.username)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return Me(username=settings.username)


@auth_router.post("/auth/logout", response_model=MessageResponse)
def logout(
    request: Request,
    response: Response,
    session_id: Annotated[str | None, Cookie()] = None,
):
    """Ends the caller's own session (other browsers stay logged in). Safe to call when logged out."""
    if session_id:
        request.app.state.sessions.delete(session_id)
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        secure=request.app.state.settings.cookie_secure,
        samesite="lax",
    )
    return MessageResponse(message="Logged out")


@auth_router.get("/me", response_model=Me)
def me(username: CurrentUser):
    return Me(username=username)


# ============================================================================
# Helpers
# ============================================================================


def next_due(last_maintenance_date: str | None, cadence_days: int | None) -> date | None:
    """Last maintenance + cadence. The one place this is computed; the frontend never re-derives it."""
    if last_maintenance_date is None or cadence_days is None:
        return None
    try:
        return date.fromisoformat(last_maintenance_date) + timedelta(days=cadence_days)
    except OverflowError:  # past 9999-12-31
        return None


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def load_item(conn: sqlite3.Connection, item_id: int) -> Item:
    row = db.get_item(conn, item_id)
    if row is None:
        raise not_found("Item")
    return Item(
        **dict(row),
        next_due=next_due(row["last_maintenance_date"], row["cadence_days"]),
        tags=db.list_item_tags(conn, item_id),
    )


def load_note(conn: sqlite3.Connection, note_id: int) -> Note:
    row = db.get_note(conn, note_id)
    if row is None:
        raise not_found("Note")
    return Note(**row)


def load_record(conn: sqlite3.Connection, record_id: int) -> MaintenanceRecord:
    row = db.get_record(conn, record_id)
    if row is None:
        raise not_found("Maintenance record")
    return MaintenanceRecord(**row)


# ============================================================================
# Item routes
#
# Every route below requires a session. PATCH bodies use exclude_unset, so an
# omitted field is left alone and an explicit null clears the column.
# mode="json" turns dates into "YYYY-MM-DD" strings for SQLite.
#
# `tags` isn't a column: it's split off the body and written by
# db.set_item_tags in the same transaction as the item's own fields.
# ============================================================================

api_router = APIRouter(prefix="/api", dependencies=[Depends(get_current_user)])


@api_router.get("/items", response_model=list[ItemSummary])
def list_items(conn: Conn):
    return [
        ItemSummary(**dict(row), next_due=next_due(row["last_maintenance_date"], row["cadence_days"]))
        for row in db.list_items(conn)
    ]


@api_router.get("/items/{item_id}", response_model=ItemDetail)
def get_item(item_id: Id, conn: Conn):
    item = load_item(conn, item_id)
    return ItemDetail(
        **item.model_dump(),
        notes=[Note(**row) for row in db.list_notes(conn, item_id)],
        maintenance_records=[MaintenanceRecord(**row) for row in db.list_records(conn, item_id)],
    )


@api_router.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemCreate, conn: Conn):
    with db.transaction(conn):
        item_id = db.insert_item(conn, body.model_dump(mode="json", exclude={"tags"}))
        if body.tags:
            db.set_item_tags(conn, item_id, body.tags)
    return load_item(conn, item_id)


@api_router.patch("/items/{item_id}", response_model=Item)
def update_item(item_id: Id, body: ItemPatch, conn: Conn):
    with db.transaction(conn):
        if not db.update_item(conn, item_id, body.model_dump(mode="json", exclude_unset=True, exclude={"tags"})):
            raise not_found("Item")
        # None only when omitted: the model rejects an explicit null.
        if body.tags is not None:
            db.set_item_tags(conn, item_id, body.tags)
    return load_item(conn, item_id)


@api_router.delete("/items/{item_id}", response_model=MessageResponse)
def archive_item(item_id: Id, conn: Conn):
    """Soft delete: sets archived_at. Notes and records are kept but hidden with the item."""
    if not db.archive_item(conn, item_id):
        raise not_found("Item")
    return MessageResponse(message="Item archived")


# ============================================================================
# Tag routes
#
# Tags are created and attached through an item's `tags` field; this only lists
# them, for the tag input's suggestions.
# ============================================================================


@api_router.get("/tags", response_model=list[TagSummary])
def list_tags(conn: Conn):
    return [TagSummary(**row) for row in db.list_tags(conn)]


# ============================================================================
# Note routes
# ============================================================================


@api_router.post("/items/{item_id}/notes", response_model=Note, status_code=status.HTTP_201_CREATED)
def create_note(item_id: Id, body: NoteCreate, conn: Conn):
    note_id = db.insert_note(conn, item_id, body.model_dump(mode="json"))
    if note_id is None:
        raise not_found("Item")
    return load_note(conn, note_id)


@api_router.patch("/notes/{note_id}", response_model=Note)
def update_note(note_id: Id, body: NotePatch, conn: Conn):
    if not db.update_note(conn, note_id, body.model_dump(mode="json", exclude_unset=True)):
        raise not_found("Note")
    return load_note(conn, note_id)


@api_router.delete("/notes/{note_id}", response_model=MessageResponse)
def delete_note(note_id: Id, conn: Conn):
    if not db.delete_note(conn, note_id):
        raise not_found("Note")
    return MessageResponse(message="Note deleted")


# ============================================================================
# Maintenance record routes
# ============================================================================


@api_router.post(
    "/items/{item_id}/maintenance_records",
    response_model=MaintenanceRecord,
    status_code=status.HTTP_201_CREATED,
)
def create_record(item_id: Id, body: MaintenanceRecordCreate, conn: Conn):
    record_id = db.insert_record(conn, item_id, body.model_dump(mode="json"))
    if record_id is None:
        raise not_found("Item")
    return load_record(conn, record_id)


@api_router.patch("/maintenance_records/{record_id}", response_model=MaintenanceRecord)
def update_record(record_id: Id, body: MaintenanceRecordPatch, conn: Conn):
    if not db.update_record(conn, record_id, body.model_dump(mode="json", exclude_unset=True)):
        raise not_found("Maintenance record")
    return load_record(conn, record_id)


@api_router.delete("/maintenance_records/{record_id}", response_model=MessageResponse)
def delete_record(record_id: Id, conn: Conn):
    if not db.delete_record(conn, record_id):
        raise not_found("Maintenance record")
    return MessageResponse(message="Maintenance record deleted")


# ============================================================================
# App factory
# ============================================================================


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Build the app. Everything is wired here rather than under __main__, so tests
    and `uvicorn --factory` get exactly the same app as `python GoldrynBackend.py`.
    """
    settings = settings or load_settings()
    configure_logging(settings.log_dir)
    db.init_db(settings.db_path)

    app = FastAPI(title="Goldryn API", version="1.0.0")
    app.state.settings = settings
    app.state.sessions = SessionStore()
    # One line per /api request; DB lines come from db._select/_write.
    app.add_middleware(RequestLogMiddleware)

    app.include_router(auth_router)
    app.include_router(api_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    # Mounted last: "/" would otherwise shadow every route registered after it.
    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


if __name__ == "__main__":
    import os

    import uvicorn
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    # The Docker image sets GOLDRYN_HOST=0.0.0.0: 127.0.0.1 inside a container
    # can't be reached from the host.
    host = os.getenv("GOLDRYN_HOST", "127.0.0.1")
    port = int(os.getenv("GOLDRYN_PORT", "8000"))
    # One worker only: sessions live in this process's memory.
    # No access log: RequestLogMiddleware already logs every /api request.
    uvicorn.run(create_app(), host=host, port=port, access_log=False)
