# Goldryn

A single-user home-maintenance tracker. Each **item** (water filter, furnace, gutters) has a color, an optional recurring **cadence** in days, freeform **notes**, and a history of **maintenance records** (date, summary, cost, contractor). The app shows when each item is next due: last maintenance date + cadence.

One login, no user table. It's self-hosted: FastAPI serves both the API and the built frontend from one process, behind Cloudflare.

## Where the details live

Read these before changing behavior. They are the source of truth, and this file only summarizes them.

- `BACKEND_DESIGN.md`: endpoints, response shapes, status codes, validation rules, auth.
- `DB_DESIGN.md`: schema and rationale, timestamp format, migrations.
- `FRONTEND_DESIGN.md`: components, animation, color mapping, toast behavior.
- `README.md`: setup and run commands.

**Scope.** Phase 1 is what exists now. Tags and search are deferred to Phase 2. The `tags`/`item_tags` tables exist in the schema, but no endpoint uses them yet.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.14, FastAPI, Pydantic v2, raw `sqlite3` (no ORM), bcrypt, uvicorn |
| DB | SQLite file, `data/goldryn.db` by default |
| Frontend | React 19 + TypeScript, Vite, Tailwind v4 (`@tailwindcss/vite`), Motion (`motion/react`, formerly Framer Motion). No router. |
| Tests | pytest (+ `httpx2` for FastAPI's TestClient), Vitest for `frontend/src/lib` |
| Manual API testing | Bruno collection in `bruno/` |

## Layout

```
backend/
  GoldrynBackend.py   create_app() factory, all routes, static mount of frontend/dist, __main__ → 127.0.0.1:8000
  GoldrynModels.py    Pydantic request/response models (mirror frontend/src/lib/GoldrynModels.tsx)
  db.py               connect(), get_db dependency, init_db() + MIGRATIONS, per-table query helpers
  auth.py             in-memory SessionStore, check_credentials, get_current_user dependency
  settings.py         env → Settings dataclass
  schema.sql          migration 1 (the full Phase 1 schema)
  hash_password.py    prints a GOLDRYN_PASSWORD_HASH line for .env
  tests/              pytest; conftest.py gives `client` (logged in) and `anon` fixtures on a temp DB
frontend/src/
  App.tsx             auth state, view mode (list/panel), toast, the `mutate` wrapper
  api/client.ts       fetch wrapper; throws ApiError(status), status 0 = unreachable
  lib/                shared types, date helpers, toast copy (unit-tested)
  components/         LoginScreen, LandingPage, ItemCard, ItemPanel, NoteCard, RecordCard, EditableField, ColorPicker, FeedbackToast
  useCreateThenUpdate.ts  save-on-blur: first save POSTs, later saves PATCH
  palette.ts          color name → {bg, accent}; unknown/null → Slate
bruno/                one request per endpoint, runs in order
run.sh                build the frontend, then serve everything on :8000
```

## Commands

Windows with Git Bash. On Linux/macOS, use `.venv/bin/` instead of `.venv/Scripts/`.

```sh
.venv/Scripts/pytest                              # backend tests
.venv/Scripts/python backend/GoldrynBackend.py    # API (+ built frontend) on http://127.0.0.1:8000
cd frontend && npm run dev                        # Vite on :5173, proxies /api to :8000
cd frontend && npm run build && npm run lint && npm test
./run.sh                                          # build frontend + serve on :8000
```

The backend needs `.env` (copy `.env.example`): `GOLDRYN_USERNAME`, `GOLDRYN_PASSWORD_HASH`, and `GOLDRYN_COOKIE_SECURE=false` for local http. Tests don't read `.env`; they build their own `Settings`.

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
- **Archiving.** Deleting an item is a soft delete (`archived_at`). Archived items and their notes and records behave as 404 everywhere. Notes and records are hard-deleted.
- **`next_due`.** Computed only on the server, by `next_due()` in `GoldrynBackend.py`. The frontend never derives it.
- **Status codes.**
  - 400: bad login.
  - 401: no or expired session. This is checked before body validation.
  - 404: missing or archived.
  - 422: validation failed.
  - The frontend maps both 400 and 422 to the "Invalid data" toast.

**Frontend**
- **Code style.** TypeScript with single quotes, no semicolons, and lines up to about 120 characters. There's no Prettier config yet, so match the surrounding code.
- **Toasts.** Every POST/PATCH/DELETE goes through App's `mutate`. It shows the toast, refetches the grid on success, and bounces to login on 401. GETs don't toast.
- **Saving.** Fields save on blur, and only when the value changed (`EditableField`). Escape blurs first so an in-progress edit is saved, then closes the panel.
- **Cards and panel.**
  - Cards use the `clip-corners` utility defined in `index.css`.
  - A new item's panel docks on the left half. An existing item's panel docks on the right 3/5.
  - The grid shifts to the other side.
- **Colors.** The backend stores a palette name such as `"Green"`, and `palette.ts` owns the actual colors.

**Repo**
- **Line endings.** `core.autocrlf=true` is on. `*.sh` is forced to LF by `.gitattributes`.
- **Workflow.**
  - Branch off `phase-one` as `p1/<topic>` and open PRs into `phase-one`, which the user merges (squash lately).
  - If one PR is stacked on another, rebase it with `--onto` after the lower PR is squash-merged.
- **Commits.** End commit messages with the `Co-Authored-By` trailer.
