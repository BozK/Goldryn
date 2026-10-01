# Deploy notes

Notes for running Goldryn on the home server. It sits next to PredictionGame (`game.boz-k.com`) and XClipboard (`pad.boz-k.com`), behind the same Caddy and Cloudflare setup, as a systemd service under its own user.

**Status (2026-09-30): paused.** The server runs DietPi, which makes installing Python 3.14 awkward, and an OS move may come first. Everything below still applies on any systemd distro. Only the Python install step depends on the OS.

## Target setup

| Piece | Value |
|---|---|
| Domain | `goldryn.boz-k.com` (DNS through Cloudflare, like the other apps) |
| Repo | `/opt/Repos/Goldryn`, owned by your login |
| Service user | `goldryn:goldryn`, a system account with no home and no shell |
| Port | `127.0.0.1:8002`. PredictionGame has 8000 and pad has 8001, so check `ss -ltn` first |
| Python | A venv at `.venv`, Python 3.14 from uv, installed under `/opt/python` |
| DB and logs | `data/goldryn.db` and `logs/` in the repo (the defaults), owned by `goldryn` |
| Config | `Environment=` lines in the unit file, no `.env` on the server |

## Decisions and why

- **Data and logs stay in the repo.** Both are gitignored, so `git pull` never touches them. The one thing to avoid is `git clean -x`, which deletes ignored files and would take the database with it. The service user owns just those two directories, so it can't write anywhere else in the repo.
- **No `.env` on the server.** The service starts through `uvicorn ... --factory`, which never calls `load_dotenv`. Only `python GoldrynBackend.py` does. `.env` stays the setup for local development.
- **`uvicorn --factory` instead of `python GoldrynBackend.py`.** `__main__` hardcodes port 8000, which PredictionGame already uses. The CLI lets us pick the port without a code change.
- **Python comes from uv.** DietPi is Debian-based, so the deadsnakes PPA (Ubuntu only) isn't an option, and apt's Python is older than 3.14. If a future OS ships 3.14 or offers it as a package, `python3.14 -m venv .venv` works too, and you can skip the uv section.

## One-time setup

### 1. Service user

```sh
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin goldryn
id goldryn                     # check: uid/gid and the goldryn group
```

Remove it with `sudo userdel goldryn`. The group goes too if nothing else is in it.

### 2. Writable directories

```sh
cd /opt/Repos/Goldryn
sudo install -d -o goldryn -g goldryn data logs
```

SQLite writes temporary journal files next to the database, so `goldryn` has to own the `data/` directory itself, not just the `.db` file. If the directories already exist, run `sudo chown -R goldryn:goldryn data logs`.

### 3. Python 3.14 and the venv (uv)

By default uv puts the Python it downloads under `~/.local/share/uv/python`, and the venv's `python` is a symlink into it. The service can't follow that link: `ProtectHome=true` hides `/home` from it, and `goldryn` couldn't read your home directory anyway. Install the interpreter under `/opt` instead:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh          # uv itself lives in ~/.local/bin; only you run it

sudo mkdir -p /opt/python
sudo chown "$USER": /opt/python
echo 'export UV_PYTHON_INSTALL_DIR=/opt/python' >> ~/.bashrc   # so later uv runs don't go back to ~
export UV_PYTHON_INSTALL_DIR=/opt/python
uv python install 3.14

cd /opt/Repos/Goldryn
rm -rf .venv                                             # the current one links into ~, so rebuild it
uv venv --seed --python 3.14 .venv                       # --seed adds pip, which prodBuild.sh uses
uv pip install --python .venv/bin/python -r requirements.txt
```

Check it:

```sh
readlink -f .venv/bin/python                             # should be under /opt/python/
sudo -u goldryn /opt/Repos/Goldryn/.venv/bin/python -c "import fastapi, bcrypt; print('ok')"
```

Afterwards, clean up the Python uv put in your home directory: `env -u UV_PYTHON_INSTALL_DIR uv python uninstall 3.14`.

### 4. Node, for building the frontend

The build needs Node 20.19+ or 22.12+ (Vite). Check `node --version`. If it's missing or too old, `dietpi-software` has a Node.js option. Without Node on the server, you can run `npm run build` on the dev machine and `scp -r frontend/dist` across. In that case you'd skip the npm half of `prodBuild.sh`.

### 5. Password hash

```sh
.venv/bin/python backend/hash_password.py
```

It prints `GOLDRYN_PASSWORD_HASH='$2b$12$...'`. The hash works on any machine, so you can generate it on Windows too. Paste the value into the unit file **without the single quotes**. Inside `Environment="..."`, they would become part of the value, and every login would fail with a 400. systemd doesn't expand `$` in `Environment=`, so the hash needs no escaping.

### 6. Unit file: `/etc/systemd/system/goldryn.service`

Modeled on `predictiongame.service`:

```ini
[Unit]
Description=Goldryn FastAPI Server
After=network.target

[Service]
Type=simple

User=goldryn
Group=goldryn

WorkingDirectory=/opt/Repos/Goldryn/backend

# One worker only (uvicorn's default): sessions live in process memory.
# --no-access-log: RequestLogMiddleware already logs every /api request.
ExecStart=/opt/Repos/Goldryn/.venv/bin/uvicorn GoldrynBackend:create_app --factory --host 127.0.0.1 --port 8002 --no-access-log

Restart=always
RestartSec=5

Environment="GOLDRYN_USERNAME=XXX"
Environment="GOLDRYN_PASSWORD_HASH=XXX"
# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

- **Leave out `GOLDRYN_COOKIE_SECURE`.** It defaults to `true`, which is right behind HTTPS.
- **`ProtectSystem=full` leaves `/opt` writable,** so `data/` and `logs/` work as they are.

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now goldryn
systemctl status goldryn
journalctl -u goldryn -f                   # stdout/stderr; the app's own log is logs/Goldryn-YYYY-MM-DD.log
curl http://127.0.0.1:8002/health          # {"status":"ok"}
```

### 7. Caddy and DNS

Add to the Caddyfile:

```
goldryn.boz-k.com {
    tls /etc/caddy/certs/boz-k.com.pem /etc/caddy/certs/boz-k.com.key
    reverse_proxy 127.0.0.1:8002
}
```

Then:
- Run `sudo systemctl reload caddy`.
- Make sure the origin cert covers `*.boz-k.com`.
- Add the `goldryn` DNS record in Cloudflare, proxied.

## Updating

```sh
cd /opt/Repos/Goldryn && git pull
./prodBuild.sh                      # npm ci + build frontend/dist, sync the venv with requirements.txt
sudo systemctl restart goldryn
```

- **A restart logs you out.** Sessions live in memory.
- **Schema migrations need nothing extra.** They run on startup.
- **Why `prodBuild.sh` uses `npm ci`:** `npm install` can rewrite `package-lock.json`, and a modified lockfile would make the next `git pull` fail.

## Already handled

- **Real client IPs.** `logger.py` logs `CF-Connecting-IP`, and Caddy passes it through. The firewall only lets in Cloudflare's IPs, plus SSH from the LAN, so the header can't be spoofed by connecting to the server directly.

## Not done yet

See `TODOs.md`: login rate limiting, database backups, and pruning old logs.
