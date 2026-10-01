# TODOs

## High Priority / Features

- **Deploy to the home server.** Paused on 2026-09-30, because installing Python 3.14 on DietPi is awkward and an OS move may come first. The plan, decisions and remaining steps are in `DEPLOY_NOTES.md`.

## Medium Priority

- **Rate limit logins.** The login endpoint is public, and nothing stops repeated guesses. bcrypt slows each attempt but doesn't cap them. Still to decide:
  - **Where it lives.** A Cloudflare rate-limiting rule needs no code but sits outside the repo. An in-app limiter is testable and versioned. Doing both is also an option.
  - **What it keys on.** The IP from `CF-Connecting-IP` (already parsed in `logger.py`), a global counter on the one account, or both. A global lockout also locks out the real user, so it probably needs a short window, not a hard lock.
  - **Response.** 429 with `Retry-After`. `LoginScreen` currently shows "Try again" for anything other than 400/401, so it needs a "Too many attempts, wait N minutes" message.
  - **State.** In memory, like sessions, so a restart clears it. That's acceptable for a single worker.

## Low Priority

- **Back up the database.** All the data is one SQLite file, `data/goldryn.db`. Back it up on a schedule (cron or a systemd timer) with `sqlite3 data/goldryn.db ".backup /path/goldryn-$(date +%F).db"`. That's safe while the app is running; a plain `cp` isn't. Prune old copies and keep at least one off the server.
- **Prune old logs.** `logs/` gets a new `Goldryn-YYYY-MM-DD.log` every day and nothing deletes the old ones. Either delete them from a cron job (`find logs -name 'Goldryn-*.log' -mtime +90 -delete`) or have `logger.py` remove files older than N days when it rolls over to a new day.
