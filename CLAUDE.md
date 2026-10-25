# Goldryn

A single-user home-maintenance tracker. Each **item** (water filter, furnace, gutters) has a color, an optional recurring **cadence** in days, freeform **notes**, a history of **maintenance records** (date, summary, cost, contractor), and uploaded **attachments** (manuals, receipts, photos). The app shows when each item is next due: last maintenance date + cadence.

One login, no user table. It's self-hosted: FastAPI serves both the API and the built frontend from one process, behind Cloudflare.

## Where the details live

Read these before changing behavior. They are the source of truth, and this file only summarizes them.

- `BACKEND_DESIGN.md`: endpoints, response shapes, status codes, validation rules, auth.
- `DB_DESIGN.md`: schema and rationale, timestamp format, migrations.
- `FRONTEND_DESIGN.md`: components, animation, color mapping, toast behavior.
- `TAGS_PHASE1.md`: the tags design end to end, including the alternatives that were rejected.
- `README.md`: setup and run commands.
- `DEPLOY.md`: home-server deployment (Docker, server layout, Caddy).
- `TODOs.md`: open work by priority.

**Scope.** Phase 1 is what exists now, tags and attachments included. Search is deferred to Phase 2. The app is desktop-only for now.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.14, FastAPI, Pydantic v2, raw `sqlite3` (no ORM), bcrypt, uvicorn, python-multipart, Pillow (previews) |
| DB | SQLite file, `data/goldryn.db` by default; uploaded files in `data/attachments/` |
| Frontend | React 19 + TypeScript, Vite, Tailwind v4 (`@tailwindcss/vite`), Motion (`motion/react`, formerly Framer Motion). No router. |
| Tests | pytest (+ `httpx2` for FastAPI's TestClient), Vitest for `frontend/src/lib` |
| Manual API testing | Bruno collection in `bruno/` |

## Layout

```
backend/
  GoldrynBackend.py   create_app() factory, all routes, static mount of frontend/dist, __main__ → 127.0.0.1:8000 (Docker sets GOLDRYN_HOST=0.0.0.0)
  GoldrynModels.py    Pydantic request/response models (mirror frontend/src/lib/GoldrynModels.tsx)
  db.py               connect(), get_db dependency, init_db() + MIGRATIONS, per-table query helpers
  auth.py             in-memory SessionStore, check_credentials, get_current_user dependency
  attachments.py      attachment files on disk: store_upload, kind detection, image previews, unique_filename
  settings.py         env → Settings dataclass
  schema.sql          migration 1 (the full Phase 1 schema)
  hash_password.py    prints a GOLDRYN_PASSWORD_HASH line for .env
  tests/              pytest; conftest.py gives `client` (logged in) and `anon` fixtures on a temp DB
frontend/src/
  App.tsx             auth state, view mode (list/panel), toast, the `mutate` wrapper
  api/client.ts       fetch wrapper; throws ApiError(status), status 0 = unreachable
  lib/                shared types, date helpers, toast copy, tag matching, attachment display helpers (unit-tested)
  components/         LoginScreen, LandingPage, ItemCard, ItemPanel, NoteCard, RecordCard, AttachmentCard, MasonryGrid, EditableField, ColorPicker, TagInput, FeedbackToast
  useCreateThenUpdate.ts  save-on-blur: first save POSTs, later saves PATCH
  palette.ts          color name → {bg, accent}; unknown/null → Slate
bruno/                one request per endpoint, runs in order
dev.sh                local: docker compose -f compose.dev.yaml up --build, on :8000
dev.ps1               same, for PowerShell
Dockerfile            frontend build stage, then Python 3.14 on :8000; targets `app` (default) and `test` (adds pytest)
compose.yaml          server: expects /srv/goldryn/{app,data,.env}; publishes it as 127.0.0.1:8002 only
compose.dev.yaml      local: `app` on 127.0.0.1:8000 with ./data and ./logs mounted; `test` runs pytest on the mounted backend/
run.sh                on the server: docker compose up -d --build
```

## Commands

The backend runs only in Docker, locally too: there's no venv. Python commands go through `compose.dev.yaml`.

```sh
docker compose -f compose.dev.yaml run --rm test  # backend tests (mounts backend/, so no rebuild needed)
./dev.sh                                          # build the image (frontend included), serve on http://127.0.0.1:8000
.\dev.ps1                                          # same, from PowerShell
cd frontend && npm run dev                        # Vite on :5173, proxies /api to :8000
cd frontend && npm run format && npm run build && npm run lint && npm test
```

The app needs `.env` in the repo root (copy `.env.example`): `GOLDRYN_USERNAME` and `GOLDRYN_PASSWORD_HASH`. `compose.dev.yaml` sets `GOLDRYN_COOKIE_SECURE=false` for local http. Tests don't read `.env`; they build their own `Settings`. The image sets `TZ=America/New_York`; set `TZ` in `.env` to change it.

## Conventions and gotchas

**Backend**
- **Env var names.** They are prefixed `GOLDRYN_`, because Windows always sets `USERNAME`.
- **Sessions.** They live in process memory, so the server must run as a single worker, and a restart logs everyone out. That's by design.
- **Timestamps.** Stored as ISO-8601 UTC with a `Z` suffix (`strftime('%Y-%m-%dT%H:%M:%SZ','now')`), never `datetime('now')`. Dates are `YYYY-MM-DD`.
- **Schema changes.** Append a new SQL string to `db.MIGRATIONS`. Never edit a shipped step. `init_db()` applies pending steps using `PRAGMA user_version`.
- **Foreign keys.** SQLite leaves them off by default, so every connection goes through `db.connect()`, which turns them on.
- **Dynamic SQL.** Column names in `SET`/`INSERT` come only from the `*_FIELDS` whitelists in `db.py`.
- **PATCH semantics** (`model_dump(exclude_unset=True)`):
  - An omitted field is left unchanged.
  - `null` clears a nullable column.
  - `null` for `name`/`body`/`date` is a 422: those fields are typed non-optional with a `None` default.
- **Writes return the resource.** POST and PATCH return the full resource. The frontend replaces its local copy with the response, so don't return just a message.
- **Tags.** They're a `tags: string[]` field on items, not their own resource. The server lowercases the names, creates any new tag, and replaces the item's links in one `db.transaction()`. `GET /api/tags` exists only for suggestions. Max 3 per item.
- **Archiving.** Deleting an item is a soft delete (`archived_at`). Archived items and their notes, records and attachments behave as 404 everywhere. Notes and records are hard-deleted. Attachments are soft-deleted like items, and their files stay on disk.
- **Attachments.** They belong to an item only; a note or record mentions a file by name in its text. Files are stored under a random name, and their `kind` (`image`/`pdf`/`text`/`file`) comes from the bytes, never the filename. Only `image`, `pdf` and `text` are served `inline`; everything is served with `nosniff`. The upload route takes the raw `Request` so the session and size checks run before the body is read. `RequestLogMiddleware` never buffers non-JSON bodies, so keep it that way.
- **`next_due`.** Computed only on the server, by `next_due()` in `GoldrynBackend.py`. The frontend never derives it. `GET /api/items` sorts by it in Python (`list_order()`): soonest due first, then cadence with no history, then no cadence.
- **Status codes.**
  - 400: bad login.
  - 401: no or expired session. This is checked before body validation.
  - 404: missing or archived.
  - 411/413: an upload without `Content-Length`, or over 50 MB. The frontend shows "File Too Large" for 413.
  - 422: validation failed.
  - 429: too many login attempts from one IP (`LoginLimiter` in `auth.py`, 5 per 15 minutes, with `Retry-After`).
  - The frontend maps both 400 and 422 to the "Invalid data" toast.

**Frontend**
- **Code style.** Prettier owns formatting (`frontend/.prettierrc.json`: single quotes, no semicolons, 120-character lines). Run `npm run format` after editing; `npm run lint` fails on unformatted files (the build doesn't check).
- **Toasts.** Every POST/PATCH/DELETE goes through App's `mutate`. It shows the toast, refetches the grid on success, and bounces to login on 401. GETs don't toast.
- **Saving.** Fields save on blur, and only when the value changed (`EditableField`). Escape blurs first so an in-progress edit is saved, then closes the panel.
- **Cards and panel.**
  - Item cards, notes and records use the `clip-corners` utility in `index.css` (a `shape()` clip-path). Tune it per element with `clip-cut-*` and `clip-round-*`, e.g. notes and records use `clip-cut-4`.
  - A new item's panel docks on the left half. An existing item's panel docks on the right 3/5.
  - The grid shifts to the other side.
- **Colors.** The backend stores a palette name such as `"Green"`, and `palette.ts` owns the actual colors.

**Repo**
- **Line endings.** `core.autocrlf=true` is on. `*.sh` is forced to LF by `.gitattributes`.
- **Workflow.**
  - Branch off `phase-one` as `p1/<topic>` and open PRs into `phase-one`, which the user merges (squash lately).
  - If one PR is stacked on another, rebase it with `--onto` after the lower PR is squash-merged.
- **Commits.** End commit messages with the `Co-Authored-By` trailer.
