# Goldryn
Maintenance Tracker on Home Items/Projects

## Backend development

The backend runs in Docker, locally as well as on the server, so the only requirement is Docker (with Compose). The image brings its own Python 3.14. Local runs use `compose.dev.yaml`; the server uses `compose.yaml`.

From the repo root:

```sh
cp .env.example .env
docker compose -f compose.dev.yaml run --rm app python backend/hash_password.py
# paste the printed line into .env, and set GOLDRYN_USERNAME

./dev.sh                                          # build the image (frontend included), serve on http://127.0.0.1:8000
docker compose -f compose.dev.yaml run --rm test  # backend tests
```

On Windows PowerShell, use `.\dev.ps1` instead of `./dev.sh`. Ctrl+C stops the server.

- **Code changes:** `./dev.sh` rebuilds the image on every start, so restart it to pick up backend or frontend changes. The tests mount `backend/` from the checkout, so they always run the current code without a rebuild.
- **Data:** `compose.dev.yaml` mounts `data/` and `logs/` from the repo. The SQLite file is created at `data/goldryn.db` on first start.
- **Cookies:** `compose.dev.yaml` sets `GOLDRYN_COOKIE_SECURE=false`, because local is plain http.
- **Sessions** live in memory, so the app runs as a single worker, and restarting it logs you out.

Every API request and DB query is logged to `logs/Goldryn-YYYY-MM-DD.log` (a new file each local day) and echoed to the terminal. See "Logging" in `BACKEND_DESIGN.md`.

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
