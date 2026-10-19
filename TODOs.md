# TODOs

## High Priority / Features

- **Deploy to the home server.** The Docker setup removes the Python 3.14 problem: the image brings its own Python. Steps are in `DEPLOY.md`.

## Medium Priority

- **Rate limit logins.** The login endpoint is public, and nothing stops repeated guesses. bcrypt slows each attempt but doesn't cap them. Still to decide:
  - **Where it lives.** A Cloudflare rate-limiting rule needs no code but sits outside the repo. An in-app limiter is testable and versioned. Doing both is also an option.
  - **What it keys on.** The IP from `CF-Connecting-IP` (already parsed in `logger.py`), a global counter on the one account, or both. A global lockout also locks out the real user, so it probably needs a short window, not a hard lock.
  - **Response.** 429 with `Retry-After`. `LoginScreen` currently shows "Try again" for anything other than 400/401, so it needs a "Too many attempts, wait N minutes" message.
  - **State.** In memory, like sessions, so a restart clears it. That's acceptable for a single worker.

## Low Priority

- **Back up the data.** Today all the data is one SQLite file, `/srv/goldryn/data/db/goldryn.db` on the server. Back it up on a schedule (cron or a systemd timer) with `sqlite3 /srv/goldryn/data/db/goldryn.db ".backup /path/goldryn-$(date +%F).db"`. That's safe while the app is running; a plain `cp` isn't. Write the script to cover all of `data/`: the DB through `.backup`, and a plain copy of everything else. That way attachments (Phase 2) are covered when they land. Prune old copies and keep at least one off the server.
- **Prune old logs.** `logs/` (`/srv/goldryn/data/logs/` on the server) gets a new `Goldryn-YYYY-MM-DD.log` every day and nothing deletes the old ones. Either delete them from a cron job (`find logs -name 'Goldryn-*.log' -mtime +90 -delete`) or have `logger.py` remove files older than N days when it rolls over to a new day.

## Phase 2

- **Attachments (PDFs, images) on items and maintenance records.** Deferred on purpose. Adding them later doesn't touch existing data:
  - **Schema.** One new `attachments` table, appended to `db.MIGRATIONS` as migration 2. Existing tables aren't altered or backfilled, and `init_db()` applies the migration on the next restart.
  - **API.** A sub-resource shaped like notes and records: `POST /api/items/{id}/attachments`, `GET /api/attachments/{id}/content`, `DELETE /api/attachments/{id}`. `ItemDetail` gains an `attachments` list next to `notes` and `maintenance_records`.
  - **Frontend.** `request()` in `api/client.ts` always sends a JSON body, so uploads need a `FormData` branch. `mutate` already takes any promise.
  - **Until then,** keep receipts and manuals in a folder per item, so attaching them later is quick.

  Decide these when building it:
  - **Storage.** Files go on disk in `data/attachments/`, named by attachment id, not the uploaded filename. The table holds metadata: `id, item_id NOT NULL, record_id NULL, filename, content_type, size, created_at`. `.gitignore` only covers `*.db`, so add `data/attachments/` to it. In Docker, `/app/data` is the `data/db/` mount, so add a `../data/attachments:/app/data/attachments` mount to `compose.yaml` (and `mkdir` it on the server first) to keep attachments in their own folder.
  - **Item or record.** Manuals belong to an item and receipts to a record, so `item_id` is required and `record_id` is optional. Records are hard-deleted. When one is deleted, its attachments either cascade or fall back to the item (`ON DELETE SET NULL`). If they cascade, the app has to delete the files itself, because the DB can't.
  - **Archived items.** Their attachments follow the existing rule: they stay on disk and return 404 everywhere.
  - **Cloudflare caching.** Cloudflare caches by file extension (pdf, jpg, png…) and leaves cookies out of its cache key. So a logged-in download at a URL ending in `.pdf`, sent without cache headers, could be cached at the edge and served to anyone. Use extensionless URLs (`/api/attachments/{id}/content`) and send `Cache-Control: private, no-store`.
  - **Serving uploaded files.** Send `X-Content-Type-Options: nosniff`. Use `Content-Disposition: inline` only for images and PDFs, and `attachment` for everything else. Otherwise an uploaded HTML or SVG file could run script on the app's own origin.
  - **Size limit.** Cloudflare's free plan caps request bodies at 100 MB. Set an app-side limit well under that, e.g. 25 MB.
  - **Dependency.** FastAPI's `UploadFile` needs `python-multipart` in `requirements.txt`.
