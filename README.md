# Goldryn
Maintenance Tracker on Home Items/Projects

## Backend development

Requires Python 3.14. On Windows, from the repo root:

```sh
py -3.14 -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt

cp .env.example .env
.venv/Scripts/python backend/hash_password.py   # paste the printed line into .env, set GOLDRYN_USERNAME

.venv/Scripts/python backend/GoldrynBackend.py  # http://127.0.0.1:8000
.venv/Scripts/pytest
```

On Linux/macOS, use `.venv/bin/` instead of `.venv/Scripts/`. The SQLite file is created at `data/goldryn.db` on first start (override with `GOLDRYN_DB_PATH`). Sessions live in memory, so run a single worker, and restarting the server logs you out.

To run it with uvicorn directly (e.g. with `--reload`), it's an app factory:

```sh
.venv/Scripts/uvicorn GoldrynBackend:create_app --factory --app-dir backend --env-file .env
```

## Frontend development

Requires Node 20.19+ or 22.12+.

```sh
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to the backend on 127.0.0.1:8000
npm run build   # type-check + production build into frontend/dist
npm run lint
```
