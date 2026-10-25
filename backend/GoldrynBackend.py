import pathlib
import sqlite3
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, FastAPI, HTTPException, Path, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

import attachments
import db
from auth import SESSION_COOKIE, SESSION_TTL, LoginLimiter, SessionStore, check_credentials, get_current_user
from GoldrynModels import (
    Attachment,
    AttachmentPatch,
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
from logger import IP_HEADER, RequestLogMiddleware, configure_logging
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
    limiter: LoginLimiter = request.app.state.login_limiter
    # Throttled per client IP, checked before bcrypt so a blocked attempt costs nothing.
    # Requests without the header (local, or tests) share one bucket.
    client = request.headers.get(IP_HEADER.decode(), "")
    retry_after = limiter.attempt(client)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
            headers={"Retry-After": str(retry_after)},
        )
    if not check_credentials(settings, credentials.username, credentials.password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid username or password")

    limiter.reset(client)

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


def find_attachment(conn: sqlite3.Connection, attachment_id: int) -> sqlite3.Row:
    row = db.get_attachment(conn, attachment_id)
    if row is None:
        raise not_found("Attachment")
    return row


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


def list_order(item: ItemSummary) -> tuple:
    """Soonest due first, so overdue items lead; then items with a cadence but no history; then no cadence.

    Sorted here rather than in SQL so next_due() stays the one place the due date is computed.
    """
    if item.next_due is not None:
        return (0, item.next_due)
    return (1,) if item.cadence_days is not None else (2,)


@api_router.get("/items", response_model=list[ItemSummary])
def list_items(conn: Conn):
    items = [
        ItemSummary(**dict(row), next_due=next_due(row["last_maintenance_date"], row["cadence_days"]))
        for row in db.list_items(conn)
    ]
    # sorted() is stable, so ties (same due date, or the same group) keep the DB's creation order.
    return sorted(items, key=list_order)


@api_router.get("/items/{item_id}", response_model=ItemDetail)
def get_item(item_id: Id, conn: Conn):
    item = load_item(conn, item_id)
    return ItemDetail(
        **item.model_dump(),
        notes=[Note(**row) for row in db.list_notes(conn, item_id)],
        maintenance_records=[MaintenanceRecord(**row) for row in db.list_records(conn, item_id)],
        attachments=[Attachment(**row) for row in db.list_attachments(conn, item_id)],
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
# Attachment routes
#
# Files belong to an item only; a note or record mentions one by name in its text.
# DELETE archives, like items: the row is hidden and the file stays on disk.
# ============================================================================

# Only these kinds open in a browser tab; any other file is always a download.
# Text always goes out as text/plain, so an uploaded .html or .svg shows as source.
INLINE_MEDIA_TYPES = {"image": None, "pdf": "application/pdf", "text": "text/plain"}
# An image or text file shown in a tab can't run anything, even if a browser misjudges it.
# Not sent for PDFs: the browser's PDF viewer won't load in a sandboxed document.
SANDBOXED_KINDS = {"image", "text"}


def too_large() -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        detail=f"File too large (max {attachments.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
    )


def save_attachment(conn: sqlite3.Connection, root: pathlib.Path, item_id: int, upload: UploadFile) -> int:
    """Write the file, then its row. If the row can't be written, the file is removed again."""
    filename = attachments.upload_filename(upload.filename or "")
    stored = attachments.store_upload(root, upload.file, filename)
    try:
        with db.transaction(conn):
            attachment_id = db.insert_attachment(
                conn,
                item_id,
                {
                    "stored_name": stored.stored_name,
                    "filename": attachments.unique_filename(filename, db.attachment_filenames(conn, item_id)),
                    "kind": stored.kind,
                    "content_type": stored.content_type,
                    "size_bytes": stored.size_bytes,
                },
            )
    except BaseException:
        attachments.delete_files(root, stored.stored_name)
        raise
    if attachment_id is None:  # the item was archived mid-upload
        attachments.delete_files(root, stored.stored_name)
        raise not_found("Item")
    return attachment_id


@api_router.post("/items/{item_id}/attachments", response_model=Attachment, status_code=status.HTTP_201_CREATED)
async def upload_attachment(item_id: Id, request: Request, conn: Conn):
    """
    One file per request, in the multipart field "file".

    Takes the raw Request rather than an UploadFile parameter: FastAPI would read
    and spool the whole body before the session check, and before the size check
    below could refuse it.
    """
    content_length = request.headers.get("content-length", "")
    if not content_length.isdigit():
        raise HTTPException(status.HTTP_411_LENGTH_REQUIRED, detail="Content-Length required")
    if int(content_length) > attachments.MAX_UPLOAD_BYTES + attachments.MULTIPART_OVERHEAD_BYTES:
        raise too_large()
    if await run_in_threadpool(db.get_item, conn, item_id) is None:
        raise not_found("Item")

    try:
        form = await request.form(max_files=1, max_fields=0)
    except StarletteHTTPException as exc:  # Starlette's 400 for a malformed form or a stray field
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.detail) from exc
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile) or not upload.filename:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Missing file")
        if upload.size is not None and upload.size > attachments.MAX_UPLOAD_BYTES:
            raise too_large()
        root = request.app.state.settings.attachments_dir
        attachment_id = await run_in_threadpool(save_attachment, conn, root, item_id, upload)
    finally:
        await form.close()

    return Attachment(**await run_in_threadpool(find_attachment, conn, attachment_id))


@api_router.patch("/attachments/{attachment_id}", response_model=Attachment)
def update_attachment(attachment_id: Id, body: AttachmentPatch, conn: Conn):
    """Rename. A name another of the item's files already has gets a " (2)" suffix."""
    with db.transaction(conn):
        row = find_attachment(conn, attachment_id)
        if body.filename is not None and body.filename != row["filename"]:
            taken = db.attachment_filenames(conn, row["item_id"], excluding_id=attachment_id)
            db.rename_attachment(conn, attachment_id, attachments.unique_filename(body.filename, taken))
    return Attachment(**find_attachment(conn, attachment_id))


@api_router.delete("/attachments/{attachment_id}", response_model=MessageResponse)
def archive_attachment(attachment_id: Id, conn: Conn):
    """Soft delete: sets archived_at. The file stays on disk."""
    if not db.archive_attachment(conn, attachment_id):
        raise not_found("Attachment")
    return MessageResponse(message="Attachment archived")


@api_router.get("/attachments/{attachment_id}/content")
def attachment_content(attachment_id: Id, request: Request, conn: Conn):
    """
    The file itself: images, PDFs and text open in the tab, anything else downloads.

    The URL has no file extension and the response is private, no-store: Cloudflare
    caches by extension and ignores cookies, so a cacheable .pdf URL could be served
    to anyone.
    """
    row = find_attachment(conn, attachment_id)
    path = attachments.file_path(request.app.state.settings.attachments_dir, row["stored_name"])
    if not path.is_file():
        raise not_found("Attachment file")

    kind = row["kind"]
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if kind in SANDBOXED_KINDS:
        headers["Content-Security-Policy"] = "sandbox"
    if kind in INLINE_MEDIA_TYPES:
        media_type, disposition = INLINE_MEDIA_TYPES[kind] or row["content_type"], "inline"
    else:
        media_type, disposition = "application/octet-stream", "attachment"
    return FileResponse(
        path,
        media_type=media_type,
        filename=row["filename"],
        content_disposition_type=disposition,
        headers=headers,
    )


@api_router.get("/attachments/{attachment_id}/preview")
def attachment_preview(attachment_id: Id, request: Request, conn: Conn):
    """A small JPEG of an image attachment. Ids are never reused, so it's cached for good."""
    row = find_attachment(conn, attachment_id)
    path = attachments.preview_path(request.app.state.settings.attachments_dir, row["stored_name"])
    if row["kind"] != "image" or not path.is_file():
        raise not_found("Preview")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=31536000, immutable", "X-Content-Type-Options": "nosniff"},
    )


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
    attachments.ensure_dirs(settings.attachments_dir)

    app = FastAPI(title="Goldryn API", version="1.0.0")
    app.state.settings = settings
    app.state.sessions = SessionStore()
    app.state.login_limiter = LoginLimiter()
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
    # The Dockerfile sets GOLDRYN_HOST=0.0.0.0: 127.0.0.1 inside a container
    # can't be reached from the host.
    host = os.getenv("GOLDRYN_HOST", "127.0.0.1")
    # One worker only: sessions live in this process's memory.
    # No access log: RequestLogMiddleware already logs every /api request.
    uvicorn.run(create_app(), host=host, port=8000, access_log=False)
