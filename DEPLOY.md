# Deploying Goldryn

Goldryn runs on the home server in Docker. It sits next to PredictionGame (`game.boz-k.com`) and XClipboard (`pad.boz-k.com`), behind the same host Caddy and Cloudflare. The image is built on the server from this checkout.

| Piece | Value |
|---|---|
| Domain | `goldryn.boz-k.com` (DNS through Cloudflare, proxied) |
| Port | `127.0.0.1:8002`. PredictionGame has 8000 and pad has 8001 |
| Container | Python 3.14, runs `backend/GoldrynBackend.py` as the `goldryn` system user, one worker |

## Server layout

```
/srv/goldryn/                owner: you
├── app/                     owner: you   <- this repo (git clone)
│   └── .env -> ../.env                   <- symlink so compose can read APP_UID/APP_GID
├── data/                    owner: goldryn:goldryn, group-writable, setgid
│   ├── db/                               <- goldryn.db (mounted at /app/data)
│   └── logs/                             <- Goldryn-YYYY-MM-DD.log (mounted at /app/logs)
└── .env                     owner: you, mode 600 <- APP_UID/APP_GID, username, password hash, TZ
```

`data/` and `.env` are the only things to back up. Run `docker compose` from `app/`.

The container runs as a dedicated `goldryn` system user, not as you. If the app were compromised and escaped the container, it would land as an unprivileged user that can't read your home directory or use Docker. You're in the `goldryn` group, so you can still read the DB and logs without sudo.

## First-time setup

```sh
# App user + folders
sudo adduser --system --group --no-create-home goldryn
sudo mkdir -p /srv/goldryn/data/db /srv/goldryn/data/logs
sudo chown $USER:$USER /srv/goldryn
sudo chown -R goldryn:goldryn /srv/goldryn/data
sudo chmod -R g+rwX /srv/goldryn/data
sudo find /srv/goldryn/data -type d -exec chmod g+s {} +
sudo usermod -aG goldryn $USER             # log out and back in for this to apply

# Code + config
git clone git@github.com:BozK/Goldryn.git /srv/goldryn/app
cp /srv/goldryn/app/.env.example /srv/goldryn/.env
chmod 600 /srv/goldryn/.env
ln -s ../.env /srv/goldryn/app/.env
id goldryn                                 # put the uid/gid into .env as APP_UID/APP_GID
```

Create `data/` yourself before the first `up`. If Docker creates the mount folders, root owns them and the container can't write to them.

`compose.yaml` refuses to run without `APP_UID`/`APP_GID` rather than fall back to a default UID. If you see "APP_UID missing", either the `.env` values or the `app/.env` symlink is missing.

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

- **Keep `127.0.0.1:` in the `ports:` mapping.** Docker-published ports bypass ufw, so a bare `8002:8000` would expose the app to the LAN and the internet.
- **Client IPs** in the log come from Cloudflare's `CF-Connecting-IP` header, which Caddy passes through. The firewall only lets in Cloudflare's IPs, so the header can't be spoofed by connecting directly.
- **Logs:** `docker compose logs -f` shows stdout/stderr. The app's own log is in `data/logs/`.
