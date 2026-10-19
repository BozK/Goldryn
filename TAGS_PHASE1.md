# Goldryn — Tags (Phase 1)

Tags were planned for Phase 2. They moved into Phase 1 so they exist before real data goes in. **Search stays in Phase 2.**

An item has up to 3 tags. You add them in the item panel by typing; a dropdown suggests tags already in use. Each tag is a chip with an × that removes it from that item.

`BACKEND_DESIGN.md`, `DB_DESIGN.md` and `FRONTEND_DESIGN.md` describe the result. This file keeps the whole design in one place, including the options that were rejected and why.

## Decisions

| Question | Decision | Why |
|---|---|---|
| API shape | `tags` is a field on the item (`POST`/`PATCH /api/items`), plus `GET /api/tags` for suggestions | One more PATCH field fits save-on-blur, "writes return the resource" and one toast per action. No tag ids on the client. |
| Who decides if a tag is new | The server, by name, in the same transaction as the item write | The client's suggestion list can be stale. Server-side find-or-create can't produce duplicates, orphans or a half-done two-call write. |
| Casing | Everything is lowercase | One spelling per tag. The existing `UNIQUE` on `tags.name` is then case-insensitive in effect, with no migration. |
| Limit | 3 tags per item, counted after duplicates are removed | Keeps tags as labels, not a second notes field. |
| Text left in the input on blur | Saved as a tag, like every other field | You can't reliably tell "half-typed" from "done". A stray tag costs one click on its ×. |
| Unused tags | Left in the table, hidden from `GET /api/tags` | No cleanup code. A tag that only archived items use comes back if the item is un-archived. |
| Suggestion order | Most-used first, then alphabetical | The tags you use most are the ones you most likely want. |
| Suggestion freshness | `App` fetches `GET /api/tags` after login and again whenever `refreshKey` changes | `mutate` already bumps `refreshKey` on every successful write, so a tag created on one item is suggested on the next. |
| Landing cards | No tags on them | The cards stay as they are. `GET /api/items` doesn't return tags. |

## Data model

There's no migration. Migration 1 already created both tables:

```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE item_tags (
    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (item_id, tag_id)
);
```

- **Case.** The API is the only writer and it lowercases every name, so `UNIQUE` on the stored value is enough. No `COLLATE NOCASE` index is needed.
- **Order on an item.** `item_tags` is an ordinary rowid table. Saving an item's tags deletes its links and inserts them in list order, so `ORDER BY item_tags.rowid` returns them in the order they were added. There's no position column.
- **Archiving.** An archived item keeps its `item_tags` rows. They're only filtered out of `GET /api/tags`.

## API

### `GET /api/tags`

Returns every tag that at least one **active** item uses, most-used first, then alphabetically:

```json
[
  { "name": "hvac", "item_count": 2 },
  { "name": "kitchen", "item_count": 1 }
]
```

It requires a session (401 without one), like every other `/api` route.

### `tags` on items

```
POST  /api/items          { "name": "Furnace", "tags": ["HVAC", "Basement"] }   optional, defaults to []
PATCH /api/items/{id}     { "tags": ["hvac"] }                                  replaces the whole set
```

- **PATCH.** An omitted `tags` leaves the item's tags alone. `[]` clears them. `null` is a 422, as with `name`.
- **Responses.** `Item` (returned by `POST`/`PATCH`) and `ItemDetail` (`GET /api/items/{id}`) include `"tags": ["hvac", "basement"]` in the order they were added. `ItemSummary` (`GET /api/items`) doesn't change.
- **Find or create.** Each name is inserted into `tags` if it's missing (`ON CONFLICT (name) DO NOTHING`) and then linked. The client never needs to know whether a tag is new.
- **One transaction.** The item's field update and its tag replacement commit or roll back together (`db.transaction()`).

### Normalization and validation

Each name is normalized before it's validated:

1. Runs of whitespace collapse to one space, and the ends are trimmed: `"  Water   heater "` → `"water heater"`.
2. It's lowercased.

Then:

- Each name is 1–32 characters after normalizing. An empty or whitespace-only name is a 422.
- Duplicates after normalizing collapse to the first occurrence: `["HVAC", "hvac"]` → `["hvac"]`.
- At most 3 names remain after removing duplicates. A 4th distinct name is a 422.
- `tags` must be a list of strings. A bare string or `null` is a 422.

## Frontend

### Where suggestions come from

`App` holds `allTags: TagSummary[]`. It fetches `GET /api/tags` once authenticated and again whenever `refreshKey` changes. A failed fetch keeps the previous list: suggestions are a convenience, and `LandingPage`'s own fetch already handles a 401. The list passes down through `ItemPanel` to `TagInput`.

### Placement

`Tags` is a new row in the panel header's `<dl>`, right after "Next maintenance". "Archive item" stays in its own row below it.

```
Color             ● ● ● ● ●
Cadence           Every 90 days
Next maintenance  Need a 3rd-party filter
Tags              [hvac ×] [basement ×] [Add a tag    ]
                                               Archive item
```

### `TagInput` behavior

- **Chips.** Each tag is a small clipped rectangle (`clip-corners clip-cut-2 clip-round-1`) filled with the item's `accent` color, with an × button labelled "Remove tag <name>".
- **Input.** It appears after the chips while the item has fewer than 3 tags. At 3, a muted "3 tags max" note replaces it.
- **New item.** The input is disabled with the placeholder "Name the item first", the same rule as "+ Add New" on Notes and Records. The item has to exist before it can be tagged.
- **Dropdown.** It opens when the input is focused. With nothing typed, it lists the most-used tags. As you type, it lists matches: names starting with the text first, then names containing it, each in most-used order. Tags already on the item are left out. If nothing matches the typed text exactly, a final `Create "<text>"` row shows that this will be a new tag. The list shows at most 8 rows.
- **Keys.**
  - ↓/↑ move the highlight. Nothing is highlighted at first.
  - Enter adds the highlighted row, or the typed text if nothing is highlighted. The input stays focused and clears, ready for the next tag.
  - Escape closes the dropdown if it's open and stops there. A second Escape reaches the panel, which blurs (saving the typed text) and closes.
- **Mouse.** Clicking a row adds it. Rows use `onMouseDown={preventDefault}` so the click doesn't blur the input first.
- **Blur.** Text left in the input is added as a tag, like every other field's save-on-blur.
- **Duplicates.** Typed text that normalizes to a tag already on the item doesn't send a request. The input just clears.

### Saving

- **Every add or remove sends the item's full tag list.** `header.save({ tags })` sends a `PATCH /api/items/{id}` through `mutate`, so each change gets one toast and refreshes the grid and suggestions.
- **Chips update immediately.** The request goes out after the chips change.
- **Saves run one at a time.** Each request carries the whole list, so out-of-order requests could otherwise leave an older list as the final state. One case where this matters: you type a tag and then click another tag's ×. The blur adds the typed tag, and then the click removes the other one.
- **A failed save puts back the last saved list.** The failure is already toasted.

## Edge cases

| Case | Result |
|---|---|
| "HVAC" typed when "hvac" exists | Links the existing "hvac" |
| "hvac" typed on an item that already has it | No request; the input clears |
| Tag removed from its only item | Disappears from suggestions on the next refresh |
| Item archived | Its tags drop out of `GET /api/tags`; the links stay in the DB |
| `PATCH` with tags on a missing or archived item | 404, and no tag rows are created |
| 4 distinct tags sent | 422; nothing changes |
| A 33-character tag | 422 (the input also stops at 32 characters) |

## Out of scope

- Renaming, merging or deleting tags. There's no `PATCH` or `DELETE /api/tags`.
- Tag colors.
- Tags on landing cards.
- Filtering and search by tag (Phase 2). Add the index on `item_tags(tag_id)` from `DB_DESIGN.md` then.

## Considered and rejected

- **Client-driven create, then attach** (`POST /api/tags`, then link). This needs a "does it exist?" check against a list that may be stale, two requests and two toasts per new tag, and handling for a tag that was created but never attached.
- **Sub-resource endpoints** (`POST /api/items/{id}/tags {name}`, `DELETE /api/items/{id}/tags/{tag_id}`). These are more REST-shaped, but they add two routes, the client has to know tag ids, and the 3-tag limit becomes a count-then-insert check.
- **Case-insensitive matching that keeps the first spelling.** This needs a `COLLATE NOCASE` index and a rule for which spelling wins. Lowercasing everything is simpler.
- **Discarding unentered text on blur.** It would be the only field in the app where blur doesn't save.
