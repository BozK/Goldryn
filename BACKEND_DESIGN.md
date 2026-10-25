# Goldryn — Backend API Design (Phase 1)

**Framework:** FastAPI
**Auth model:** Single-user, cookie-based sessions, no `users` table — credentials come from environment variables in Prod.

## Endpoints

### Auth

```
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/me
```

### Items

```
GET    /api/items              # landing page list
GET    /api/items/{id}         # detail view (item + notes + maintenance_records)
POST   /api/items              # create
PATCH  /api/items/{id}         # partial update (name, color, cadence_days, next_maintenance_notes, tags)
DELETE /api/items/{id}         # soft delete (sets archived_at)
```

### Tags

```
GET    /api/tags               # tags in use, for the tag input's suggestions
```

Tags are created, attached and removed through an item's `tags` field, not their own endpoints. See `TAGS_PHASE1.md`.

### Notes

```
POST   /api/items/{id}/notes
PATCH  /api/notes/{id}
DELETE /api/notes/{id}
```

### Maintenance Records

```
POST   /api/items/{id}/maintenance_records
PATCH  /api/maintenance_records/{id}
DELETE /api/maintenance_records/{id}
```

### Attachments

```
POST   /api/items/{id}/attachments        # multipart upload, one file in the field "file"
PATCH  /api/attachments/{id}              # rename (filename only)
DELETE /api/attachments/{id}              # soft delete (sets archived_at); the file stays on disk
GET    /api/attachments/{id}/content      # the file: inline for images, PDFs and text, otherwise a download
GET    /api/attachments/{id}/preview      # 800px JPEG preview, images only
```

**Deferred to Phase 2:** search. Tags moved into Phase 1; `TAGS_PHASE1.md` has the full design.

## Response shapes

**`GET /api/items`** — one row per active item:

```json
{
  "id": 1,
  "name": "Water filter",
  "color": "Blue",            // palette name; the frontend owns what it looks like
  "cadence_days": 90,
  "next_due": "2026-11-13"   // null if no cadence or no maintenance history yet
}
```

**`GET /api/items/{id}`** — everything else, in full:

```json
{
  "id": 1,
  "name": "Water filter",
  "color": "Blue",
  "cadence_days": 90,
  "next_maintenance_notes": "Need a 3rd-party filter, not OEM",
  "created_at": "2026-01-04T12:00:00Z",
  "next_due": "2026-11-13",
  "tags": ["kitchen", "filters"],   // lowercase, in the order they were added
  "notes": [ { "id": 1, "body": "...", "created_at": "..." } ],
  "maintenance_records": [
    { "id": 1, "date": "2026-08-15", "summary": "...", "cost": 45.00, "contractor_info": "..." }
  ],
  "attachments": [
    {
      "id": 1,
      "filename": "filter-receipt.png",
      "kind": "image",               // image | pdf | text | file, decided from the contents
      "content_type": "image/png",
      "size_bytes": 31744,
      "created_at": "2026-10-20T19:16:10Z"
    }
  ]
}
```

Items are ordered by `next_due`, soonest first, so overdue items lead. Items with no `next_due` (no cadence, or no maintenance history yet) come last. Ties keep creation order. The route handler sorts after computing `next_due`, so the due date is still computed in one place.

Notes are ordered newest first (`created_at DESC, id DESC`), maintenance records by `date DESC, id DESC`, attachments newest first (`created_at DESC, id DESC`, active ones only).

**`GET /api/tags`** — tags that at least one active item uses, most-used first, then by name:

```json
[
  { "name": "hvac", "item_count": 2 },
  { "name": "kitchen", "item_count": 1 }
]
```

**Writes return the resource.** `POST`/`PATCH /api/items[/{id}]` return the item header (every field above except `notes` and `maintenance_records`, `next_due` and `tags` included). Note and maintenance record `POST`/`PATCH` return that note or record, and attachment `POST`/`PATCH` return the attachment. The frontend's save-on-blur replaces its local copy with whatever comes back, so this is required, not a convenience. `DELETE`s return `{"message": "..."}`.

## Status codes and validation

| Code | When |
|------|------|
| 200 / 201 | Success; every `POST` that creates something returns 201 |
| 400 | Bad login credentials |
| 401 | No session, unknown session, or expired session (checked before the body is validated) |
| 404 | Missing **or archived** item; missing note/record, or one whose item is archived (including creating one under an archived item); missing or archived attachment, or one whose item is archived |
| 411 | An upload without `Content-Length` |
| 413 | An upload over 50 MB, judged by `Content-Length` before the body is read, and by the file's size after |
| 422 | Body failed validation (FastAPI's default `{"detail": [...]}`), or an upload with no `file`, more than one file, any other field, or a malformed form; the frontend shows the same "Invalid data" toast as for 400 |
| 429 | Too many login attempts from one IP; `Retry-After` gives the wait in seconds |

Validation rules:

- Unknown fields are rejected (422), so a typo'd field name doesn't silently do nothing.
- **PATCH is a merge.** An omitted field is left alone; an explicit `null` clears a nullable column. `name`, `body` and `date` are `NOT NULL`, so `null` for them is a 422. An empty PATCH body returns the resource unchanged.
- `name`: 1–200 characters after trimming whitespace.
- `color`: any string up to 32 characters. The frontend owns the palette and falls back to a neutral color for unknown names, so the backend doesn't keep a second copy of the list.
- `cadence_days`: integer from 1 to 36500 (100 years) or null.
- `body`: must contain a non-whitespace character.
- `date`: `YYYY-MM-DD` and a real calendar date. No timestamps or other formats.
- `cost`: number ≥ 0 or null.
- `tags`: a list of names. Each is trimmed, has inner whitespace collapsed to single spaces, and is lowercased, then must be 1–32 characters. Duplicates collapse to the first occurrence, after which at most 3 may remain. On `PATCH` the list replaces the item's tags; `[]` clears them and `null` is a 422. A name that doesn't exist yet is created.
- `filename` (upload or rename): anything before the last `/` or `\` is dropped, control characters are removed, and whitespace is collapsed and trimmed. A rename must then be 1–255 characters; an upload's name is cut to 255 and falls back to `file`. If another of the item's active attachments already has the name, a ` (2)`, ` (3)`… suffix goes before the extension, so a note can name a file unambiguously.
- Path ids must be positive integers in SQLite's 64-bit range (422 otherwise).

## Design notes

- **`next_due` is computed server-side, not sent as raw components.** The frontend never re-derives it from `cadence_days` + last maintenance date — one source of truth for the calculation. `GET /api/items` query:

  ```sql
  SELECT i.id, i.name, i.color, i.cadence_days,
         MAX(m.date) AS last_maintenance_date
  FROM items i
  LEFT JOIN maintenance_records m ON m.item_id = i.id
  WHERE i.archived_at IS NULL
  GROUP BY i.id
  ```

  `LEFT JOIN` is required here — an `INNER JOIN` would silently drop any item that has never had a maintenance record logged. `next_due = last_maintenance_date + cadence_days` is then computed in the route handler; `None` if either input is missing.

- **Auth mirrors the ClipBackend reference, minus the `Users` table.** Username and password are compared against `GOLDRYN_USERNAME` / a bcrypt hash in `GOLDRYN_PASSWORD_HASH` (not `USERNAME`: Windows always sets that to the OS login name). The app refuses to start if either is missing. Username comparison uses `secrets.compare_digest` rather than `==` to avoid a timing side-channel, and `bcrypt.checkpw` runs even when the username is wrong, so both failures take the same time. Bad credentials return **400**.
  - Sessions are in memory: `dict[session_id, (username, expires_at)]`, with `session_id = secrets.token_urlsafe(32)`. A server restart invalidates all sessions, which matches the "logged in until restart or 7 days" requirement. The 7-day expiry is also checked server-side, not only via the cookie's `max_age`.
  - Because sessions live in process memory, the server **must run as a single worker**.
  - Logout removes the session named by the caller's own cookie (ClipBackend removed the first session for that username, which logs out the wrong browser once there are two). Logout without a session is a harmless 200.
  - Login is rate limited per client IP (`LoginLimiter` in `auth.py`): 5 attempts per 15 minutes, then **429** with `Retry-After` until the oldest attempt ages out. The IP comes from `CF-Connecting-IP`; requests without it (local runs, tests) share one bucket. Each attempt is counted before bcrypt runs, so parallel requests can't slip past the check, and a blocked attempt costs no bcrypt time. A successful login clears the IP's count. Counts live in memory, like sessions. There's deliberately no per-account lockout: anyone could trigger it and lock the real user out. A Cloudflare rate limiting rule on the login path also drops floods before they reach the server.
  - Every `/api` route except login and logout requires a session and returns **401** without one.
  - Cookie `session_id`: `httponly=True, samesite="lax", max_age=604800`, `secure` from `GOLDRYN_COOKIE_SECURE` (default true; set it to false for local development over plain http, or browsers won't send the cookie back).

- **Soft delete stays behind a real `DELETE`.** `DELETE /api/items/{id}` sets `archived_at` rather than removing the row; the HTTP verb describes client-facing intent, not the storage mechanism. `GET /api/items` and `GET /api/items/{id}` filter `WHERE archived_at IS NULL`. Notes and maintenance records are NOT soft-deleted — the soft-delete rationale (avoid losing history) doesn't apply to records that were themselves the history being preserved; those get hard `DELETE`s.

- **REST naming: plural collections, even for single-item operations.** `/api/items`, `/api/items/{id}`, `/api/items/{id}/notes` — consistent with GitHub/Stripe-style conventions, deliberately diverging from the singular `/api/clip/{clip_id}` pattern in the ClipBackend reference.

- **PATCH, not PUT, for edits.** All edit calls send partial field sets (e.g. just `color`); PATCH is the semantically correct verb for a merge-style partial update, where PUT implies the client sends (and server replaces with) the full resource representation.

- **First-note-as-blurb (Phase 1 stretch goal only).** If implemented, avoid an N+1 query. At this scale, a correlated subquery is simplest:

  ```sql
  SELECT i.*,
    (SELECT body FROM notes
     WHERE item_id = i.id
     ORDER BY created_at ASC LIMIT 1) AS blurb
  FROM items i
  ```

  A window-function equivalent (`ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY created_at ASC)`, filtered to `rn = 1`) works too and generalizes better if this pattern shows up elsewhere later, but isn't necessary at this scale.

- **No stored procedures.** SQLite doesn't support them in the Postgres/MySQL sense anyway, and nothing about this app's scale (single user, single process, low write volume) calls for pushing logic into the DB layer. Plain parameterized queries via small per-table helper functions, same pattern as ClipBackend's `get_user_by_username`.

- **Single process, single worker.** Sessions live in memory (see auth above). It always runs in Docker as `python backend/GoldrynBackend.py`, which serves the API and the built `frontend/dist` on port 8000; the Dockerfile sets `GOLDRYN_HOST=0.0.0.0`. Locally, `./dev.sh` (`compose.dev.yaml`) publishes it as `127.0.0.1:8000`. On the server, `compose.yaml` publishes it as `127.0.0.1:8002` (see `DEPLOY.md`). `GET /health` is an unauthenticated liveness check.

- **Tags are a field on the item, not a resource of their own.** The client sends names; the server finds or creates each tag and replaces the item's links in the same transaction as the item's other fields (`db.transaction()`), so the client never has to know whether a tag is new. `GET /api/tags` exists only for suggestions and leaves out tags no active item uses. No migration was needed: the `tags` / `item_tags` tables shipped in migration 1. Full design and the rejected alternatives: `TAGS_PHASE1.md`.

- **Attachments belong to an item only.** Notes and records don't own files; one mentions a file by name in its text. So deleting a note or record never touches a file. Deleting an attachment archives it like an item: `archived_at` hides the row, and the file and its preview stay on disk. Archived attachments, and every attachment of an archived item, return 404 everywhere. Linking a record to a file properly is in `TODOs.md`.
  - **Storage.** Files live in `data/attachments/` (`Settings.attachments_dir`) under a random `stored_name`, never the uploaded name. Previews are `previews/<stored_name>.jpg`. The upload writes the file first and then the row; if the row can't be written, the file is deleted again. A crash in between leaves a harmless orphan file rather than a row with no file.
  - **Kind.** Decided from the bytes, never from the filename or the browser's `Content-Type`. `image`: Pillow decodes it as JPEG, PNG, GIF, WebP or BMP; it gets an 800px JPEG preview (EXIF-rotated, transparency flattened onto white). `pdf`: starts with `%PDF-`. `text`: the extension says `text/*` and the first 8 KB are UTF-8 with no NUL bytes. Anything else is `file`. Renaming doesn't change the kind.
  - **Upload order.** The route takes the raw `Request`, not an `UploadFile` parameter, because FastAPI would read and spool the whole body before the session check. The order is: 401, then 411/413 from the headers, then 404 for a missing item, and only then is the form parsed (`max_files=1, max_fields=0`).
  - **Serving.** Every response has `X-Content-Type-Options: nosniff`. Only `image`, `pdf` and `text` are `inline`; text always goes out as `text/plain`, so an uploaded HTML or SVG file shows as source. Inline images and text also get `Content-Security-Policy: sandbox`. PDFs don't, because browsers' PDF viewers won't load in a sandboxed document. `file` is `application/octet-stream` with `Content-Disposition: attachment`.
  - **Caching.** Cloudflare caches by file extension and leaves cookies out of its cache key, so URLs have no extension and content is `Cache-Control: private, no-store`. Previews are `private, max-age=31536000, immutable`: the table uses `AUTOINCREMENT`, so an id is never reused for a different file.
  - **Size.** 50 MB per file, under Cloudflare's 100 MB request limit.

## Logging

Every `/api/*` request and every DB query a route makes gets one line, in `backend/logger.py`. Fields are separated by ` | `, and an empty field is `-`:

```
<local time> | API | <status>          | <method> <path> | <request JSON> | <response JSON>          | <ms> | IP: <addr>
<local time> | DB | OK or ERROR <exc> | <table>: <SQL>  | <params>       | <rows, or rowcount/id>   | <ms> | IP: <addr>
```

(Padded here for reading; real lines use a single ` | `.)

```
2026-09-25 15:59:25 | API | 200 | POST /api/auth/login | {"username": "smoke", "password": "***"} | {"username": "smoke"} | 2.4ms
2026-09-25 15:59:25 | DB | OK | items: UPDATE items SET next_maintenance_notes = ? WHERE id = ? AND archived_at IS NULL | ["Need a 3rd-party filter, not OEM", 1] | rowcount=1 | 4.9ms
```

- **Where.** `logs/Goldryn-YYYY-MM-DD.log`, also echoed to stderr. A new file starts at local midnight. Nothing is renamed or deleted: the files are the history. `DailyFileHandler` checks the date on each write and opens the new day's file itself, because `TimedRotatingFileHandler`'s rename at rollover is fragile on Windows.
- **What's not logged.** `/health`, the static frontend, `init_db()`/migrations and the `PRAGMA foreign_keys` in `db.connect()`. uvicorn's own access log is off, so requests aren't logged twice.
- **Redaction.** Any `password` key in a logged body becomes `"***"`, at any depth, including where FastAPI's 422 detail echoes it back. Cookies, headers and the session id are never logged. A body that isn't JSON is logged only as `<N bytes, not JSON>`.
- **Uploads and downloads.** A request whose `Content-Type` is set and isn't JSON (an upload) streams straight to the route and is logged as `<N bytes, not JSON>` from its `Content-Length`; the middleware never holds it in memory. A response that isn't JSON (a file or preview) is only counted, the same way. Requests with no `Content-Type` are buffered like JSON, since FastAPI parses them as JSON.
- **Truncation.** Request, response, SQL params and DB rows are each cut to 200 characters, with `…(+N chars)`.
- **IP.** Taken only from Cloudflare's `CF-Connecting-IP`. Without it the field is left off; the socket address is always Cloudflare or the tunnel, so it's never used. DB lines carry the IP of the request that ran them.
- **DB lines** come from `db._select` / `db._write`, the only two places the query helpers execute SQL. The table is the first `FROM`/`INTO`/`UPDATE` target, so a JOIN or subselect is logged under its primary table. A query that raises is logged as `ERROR <ExceptionClass>: <message>` and the exception still propagates.

## Open considerations

- **Note/maintenance record edits.** `PATCH` endpoints for both are included above for completeness, but if Phase 1 scope needs trimming, these are the first candidates to defer — delete-and-recreate is a workable stopgap for fixing a bad entry.
- **Blurb query.** Only build this if the Phase 1 stretch goal is actually pursued; otherwise the `GET /api/items` query above is sufficient as-is.
