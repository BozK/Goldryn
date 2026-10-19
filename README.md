# Goldryn
Maintenance Tracker on Home Items/Projects

## Backend development

Requires Python 3.14. On Windows, from the repo root:

```sh
py -3.14 -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt

cp .env.example .env
.venv/Scripts/python backend/hash_password.py   # paste the printed line into .env, set GOLDRYN_USERNAME,
                                                # and uncomment GOLDRYN_COOKIE_SECURE=false

.venv/Scripts/python backend/GoldrynBackend.py  # http://127.0.0.1:8000
.venv/Scripts/pytest
```

On Linux/macOS, use `.venv/bin/` instead of `.venv/Scripts/`. The SQLite file is created at `data/goldryn.db` on first start (override with `GOLDRYN_DB_PATH`). Sessions live in memory, so run a single worker, and restarting the server logs you out.

Every API request and DB query is logged to `logs/Goldryn-YYYY-MM-DD.log` (a new file each local day, override the folder with `GOLDRYN_LOG_DIR`) and echoed to the terminal. See "Logging" in `BACKEND_DESIGN.md`.

To run it with uvicorn directly (e.g. with `--reload`), it's an app factory. `--no-access-log` stops uvicorn logging each request a second time:

```sh
.venv/Scripts/uvicorn GoldrynBackend:create_app --factory --app-dir backend --env-file .env --no-access-log
```

## Running it all

```sh
./dev.sh   # builds frontend/dist, then serves it and the API on http://127.0.0.1:8000
```

On Windows PowerShell, use `.\dev.ps1` instead. (`run.sh` is the server's Docker deploy script.)

## Deploying

On the home server, Goldryn runs in Docker, behind Caddy and Cloudflare. The image is built on the server from the checkout. The database, logs and `.env` live outside the repo. `DEPLOY.md` covers the one-time setup.

To update after setup:

```sh
cd /srv/goldryn/app && git pull && ./run.sh   # docker compose up -d --build; logs you out: sessions live in memory
```

## Manual API testing (Bruno)

`bruno/` is a [Bruno](https://www.usebruno.com/) collection covering every endpoint on its happy path, in order (login, CRUD, archive, logout). IDs from each create are passed to the requests after it, and Bruno's cookie jar carries the session. Pick the `local` environment and set the `username` and `password` secrets, which Bruno keeps locally and never writes to the collection files. It needs `GOLDRYN_COOKIE_SECURE=false`, since the local server is plain http. Error cases are covered by pytest, not Bruno.

## Frontend development

Requires Node 20.19+ or 22.12+.

```sh
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to the backend on 127.0.0.1:8000
npm run build   # type-check + production build into frontend/dist
npm run lint    # oxlint + Prettier check
npm run format  # Prettier: rewrite files into the house style
```
