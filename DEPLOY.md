# Deploying Goldryn

Goldryn runs on the home server in Docker. It sits next to PredictionGame (`game.boz-k.com`) and XClipboard (`pad.boz-k.com`), behind the same host Caddy and Cloudflare. The image is built on the server from this checkout.

| Piece | Value |
|---|---|
| Domain | `goldryn.boz-k.com` (DNS through Cloudflare, proxied) |
| Port | `127.0.0.1:8002`. PredictionGame has 8000 and pad has 8001 |
| Container | Python 3.14, runs `backend/GoldrynBackend.py` as UID 1000, one worker |

## Server layout

```
/srv/goldryn/
├── app/      <- this repo
├── data/
│   ├── db/   <- goldryn.db (mounted at /app/data)
│   └── logs/ <- Goldryn-YYYY-MM-DD.log (mounted at /app/logs)
└── .env      <- username, password hash, optional TZ
```

`docker compose` must be run from `app/`.

## First-time setup

```sh
sudo mkdir -p /srv/goldryn && sudo chown "$USER": /srv/goldryn
cd /srv/goldryn
git clone <repo-url> app
mkdir -p data/db data/logs                 # before the first `up`, or Docker creates them as root
cp app/.env.example .env
```

The container runs as UID 1000, so `data/` must be owned by UID 1000. Check with `id -u`. If your login has a different UID, put `APP_UID=<uid>` in your shell environment when building (`APP_UID=$(id -u) ./run.sh`).

Set the password hash. This builds the image the first time:

```sh
cd /srv/goldryn/app
docker compose run --rm goldryn python backend/hash_password.py
```

Paste the printed `GOLDRYN_PASSWORD_HASH='...'` line into `../.env` **with** its single quotes. Without them, compose reads the `$`s in the hash as variables, and every login fails. Also set `GOLDRYN_USERNAME`.

In the server's `.env`, leave `GOLDRYN_COOKIE_SECURE` unset. It defaults to `true`, which is correct behind HTTPS.

Start it:

```sh
./run.sh
curl http://127.0.0.1:8002/health          # {"status":"ok"}
```

The database is created on first start, and schema migrations run on every start. No init step is needed.

### Caddy and DNS

Add to the Caddyfile:

```
goldryn.boz-k.com {
    tls /etc/caddy/certs/boz-k.com.pem /etc/caddy/certs/boz-k.com.key
    reverse_proxy 127.0.0.1:8002
}
```

Then run `sudo systemctl reload caddy`, and add the `goldryn` DNS record in Cloudflare, proxied.

## Updating

```sh
cd /srv/goldryn/app && git pull && ./run.sh
```

The old container keeps serving until the new image builds. **The restart logs you out,** because sessions live in memory.

## Notes

- **Keep `127.0.0.1:` in the `ports:` mapping.** Docker-published ports bypass ufw, so a bare `8002:8002` would expose the app to the LAN and the internet.
- **Client IPs** in the log come from Cloudflare's `CF-Connecting-IP` header, which Caddy passes through. The firewall only lets in Cloudflare's IPs, so the header can't be spoofed by connecting directly.
- **Logs:** `docker compose logs -f` shows stdout/stderr. The app's own log is in `data/logs/`.
