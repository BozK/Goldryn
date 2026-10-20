# TODOs

## High Priority / Features

## Medium Priority

## Low Priority

- **Back up the data.** The data is one SQLite file, `/srv/goldryn/data/db/goldryn.db` on the server, plus uploaded files in `/srv/goldryn/data/attachments/`. Back the DB up on a schedule (cron or a systemd timer) with `sqlite3 /srv/goldryn/data/db/goldryn.db ".backup /path/goldryn-$(date +%F).db"`. That's safe while the app is running; a plain `cp` isn't. Write the script to cover all of `data/`: the DB through `.backup`, and a plain copy of everything else, which includes `data/attachments/`. Prune old copies and keep at least one off the server.
- **Prune old logs.** `logs/` (`/srv/goldryn/data/logs/` on the server) gets a new `Goldryn-YYYY-MM-DD.log` every day and nothing deletes the old ones. Either delete them from a cron job (`find logs -name 'Goldryn-*.log' -mtime +90 -delete`) or have `logger.py` remove files older than N days when it rolls over to a new day.
- **Link notes and records to attachments.** Attachments belong only to an item, and for now a note or record mentions one by name in its text ("See furnace-receipt.pdf"). Filenames are unique within an item for that reason. Build one of these only if plain-text references start to fall short in day-to-day use:
  - **Frontend-only auto-links.** When the panel shows a note or record, it turns text that matches one of the item's active attachment names into a link to that file. No backend or schema change. An archived file's name just goes back to being plain text. The cost is all in the frontend: links inside click-to-edit fields need care, so clicking a link opens the file instead of starting an edit.
  - **A real reference.** A migration adds a nullable `attachment_id` column to `maintenance_records` (and maybe `notes`). PATCH checks that the attachment belongs to the same item. The record shows a clickable chip, and the UI needs a picker to set it. Archiving the file doesn't break anything: the row still exists, and the frontend shows nothing because it isn't in the item's active list. Don't put a `record_id` on `attachments` instead: that makes the record the file's owner again, and a hard-deleted record would then have to decide what happens to its files.
- **Purge archived attachments.** Archiving keeps the file on disk, so `data/attachments/` only grows. If it ever matters, add a script that deletes the files of attachments archived more than N days ago (and their previews in `previews/`).
