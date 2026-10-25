# Goldryn — Frontend Design (Phase 1)

**Framework:** React
**Styling:** Tailwind CSS
**Animation:** Framer Motion
**Routing:** None — single page, all navigation is component/state driven, no URL state
**Mobile:** Out of scope for Phase 1 (stretch goal, deferred)

## Components

Three real "screens," rendered by state rather than routes, plus one always-mounted feedback popup:

```
App
├── LoginScreen
├── LandingPage
├── ItemPanel        (shared: Detail View AND New Item form)
└── FeedbackToast     (app-root level, always mounted)
```

Top-level app state:

```js
viewMode: "list" | "panel";
selectedItemId: number | null; // null => ItemPanel renders in "new" mode
```

`ItemPanel` is a single component, not two. Mode is derived, not stored:

```js
const isNew = selectedItemId === null;
```

First save in "new" mode fires `POST /api/items`; the response's `id` is written into `selectedItemId`, which flips the component into "existing" mode for every field after that — no explicit mode flag to keep in sync.

---

### 1. LoginScreen

- "Goldryn" title, username field, password field, login button — standard form, no surprises.
- Submit → `POST /api/auth/login`. Backend sets the session cookie; frontend just needs to notice a 2xx and switch `viewMode`/render the Landing Page.
- Failure → FeedbackToast shows an error ("Invalid username or password" on 400; "Too many attempts — wait N minutes" on 429, with N from `Retry-After`; generic "Try again" on 5xx). The copy lives in `loginErrorText()` in `lib/feedback.ts`.

### 2. LandingPage

- Fetches `GET /api/items` on mount.
- Renders a grid of parallelogram cards (see **Card shape** below) plus a `+` control to the left of the grid for creating a new item.
- Each card: `name`, background/accent colors resolved from the backend's generic `color` field via the frontend palette map, and `next_due` if present.
- Click a card → `selectedItemId = item.id`, `viewMode = 'panel'`.
- Click `+` → `selectedItemId = null`, `viewMode = 'panel'`.
- Empty state: no items yet is just an empty grid with the `+` control still visible. No placeholder copy needed.

**Card shape:** clipped-corner rectangle via `clip-path: polygon(...)` (or the skew-outer/unskew-inner trick if that renders text more cleanly). Fixed width and height, non-overlapping, laid out in a standard grid/masonry — dead space in the corners is an accepted tradeoff for the look. True overlapping cards are explicitly **not** a Phase 1 goal (see Open Considerations).

### 3. ItemPanel (Detail View / New Item form)

Shared layout, top to bottom:

1. **Header block** — `name` (large), `color` (palette picker), `cadence_days`, `next_maintenance_notes`, `tags` (up to 3 chips plus a type-ahead input, see `TAGS_PHASE1.md`), and (existing items only) `created_at`. All click-to-edit.
2. **Notes section** — 2-column masonry (`MasonryGrid`: each card goes under whichever column ends first, so a short card next to a tall one leaves no gap), `+ Add New` control, sorted newest-first. Each note is a styled click-to-edit text wrapper (Keep-style), not a raw `<textarea>`.
3. **Maintenance records section** — same 2-column masonry, `+ Add New`, sorted newest-first by `date`. Each record is its own rounded-rectangle card with three independently click-to-edit fields: `summary`, `cost`, `contractor_info`.
4. **Attachments section** — same 2-column masonry, `+ Attach File` (opens the file picker), newest first. Each file is an `AttachmentCard` in the same clipped shape: images show their preview across the top of the card; other files show a type badge (`PDF`, `DOCX`…). The filename is click-to-edit (a rename). The preview, the badge and the `Open ↗`/`Download` link open the file: images, PDFs and text in a new tab, anything else as a download. The hover `×` archives it after a confirm. While the section is empty, a hint says files can be dropped on the panel.

In "new" mode, the Notes, Maintenance Records and Attachments sections' add controls are disabled until the header block's first field save succeeds and `selectedItemId` is populated — `item_id` is a `NOT NULL` FK on all three, so there's nothing to attach them to before the item exists.

**Uploading:** dropping files anywhere on the panel, or picking several in the file picker, uploads them one request at a time, in order. Each one gets its own toast through `mutate`. While a file uploads, a pulsing "Uploading …" card stands in for it. A file over 50 MB gets the "File Too Large" toast without being sent. While files are dragged over the panel, an overlay says "Drop to attach" ("Name the item first" in new mode). A file dropped outside the panel is ignored, instead of the browser navigating to it.

**Save model:** every editable field saves independently on blur — no submit button anywhere in this panel.

- New item, first field blur → `POST /api/items` (subsequent header fields → `PATCH /api/items/{id}`)
- Existing item header field blur → `PATCH /api/items/{id}`
- Tag added (Enter, a picked suggestion, or blur with text in the input) or removed (its ×) → `PATCH /api/items/{id}` with the item's full tag list. Tags can't be added until the item exists.
- New/edited note blur → `POST /api/items/{id}/notes` or `PATCH /api/notes/{id}`
- New/edited maintenance record field blur → `POST /api/items/{id}/maintenance_records` or `PATCH /api/maintenance_records/{id}`
- Attachment filename blur → `PATCH /api/attachments/{id}` (uploads aren't save-on-blur; see **Uploading** above)

**Closing the panel:** an `X` in the top-right, click-outside, or `Escape`. All three close paths need any in-flight edit saved first:

- `X` and click-outside close naturally rely on native event ordering — `blur` fires before the `click` that triggers the close, so the field's save is already in flight by the time the panel starts closing. The outside-click listener must be a plain `click` (or `mousedown` without `preventDefault()`) — `preventDefault()` on `mousedown` (a common pattern in dropdown/menu libraries to keep focus put) would suppress the blur and silently drop the edit.
- `Escape` doesn't move focus on its own, so it gets an explicit flush: `document.activeElement?.blur()` before flipping `viewMode` back to `'list'`.
- The tag input's open dropdown takes the first `Escape` (it stops propagation and only closes the list); the next one reaches the panel as usual.

**Tag suggestions:** `App` fetches `GET /api/tags` after login and again whenever `refreshKey` changes (every successful write), and passes the list down to the panel's tag input.

### 4. FeedbackToast

- Lives at the app root, sibling to `ItemPanel` and `LandingPage` — not nested inside the panel, so it isn't affected by the panel's mount/unmount animation and a save response arriving after the panel has already started closing doesn't cause a "set state on unmounted component" issue.
- Slides down briefly from the top of the page on every `POST`/`PATCH`/`DELETE`:
  - Success → "Saved"
  - 400 → "Error Saving — Invalid data"
  - 401/403 → "Error Saving — Session Expired, Please Log In"
  - 413 → "Error Saving — File Too Large (max 50 MB)"
  - 5xx → "Error Saving — Try Again"
- Dumb by design: no retry queue, no held form state on error.

---

## Animation

Framer Motion handles both pieces:

- **List shift.** Cards use Framer's `layout` prop; when `viewMode` flips to `'panel'`, the grid container's width/position change is auto-animated — no manual transform math for "the cards shift left."
- **Panel slide-in.** `ItemPanel` is wrapped in `AnimatePresence`, entering with `initial={{ x: isNew ? '-100%' : '100%' }}` / `animate={{ x: 0 }}` — new-item slides in from the left, existing-item detail slides in from the right, matching the two documented flows.

## Color mapping

- Backend `color` field is a generic name (e.g. `"Green"`), not a CSS value — the frontend owns the palette.
- 20 presets, each resolving to a darker background shade (card/header background) and a lighter accent shade (the notes/maintenance-record wrapper backgrounds), with white text throughout:

  ```js
  const PALETTE = {
    Green: { bg: "#1b4332", accent: "#40916c" },
    Blue: { bg: "#1e3a5f", accent: "#4a7fb5" },
    // ...18 more
  };
  ```

- `PALETTE`'s insertion order is the picker's order: around the hue wheel, then the earthy and grey shades. Stored items keep a color's name, so a preset can be retuned but never renamed or removed. Every shade keeps white text at a contrast of at least 3:1.

- App is dark-mode-by-default; no light theme planned for Phase 1.

## Validation

- Minimal by design. Only numeric fields (`cost`) get a client-side check before firing the save call; on failure, reuse the FeedbackToast's "Invalid data" state rather than a separate inline error.
- Everything else is sent as-is and relies on the backend's own validation/error responses.

## Design notes

- **`ItemPanel` reuse over two components.** New Item and Detail View are the same layout with the same save-on-blur mechanics; the only structural difference is whether `notes`/`maintenance_records` are addable yet. One component with a derived `isNew` flag avoids duplicating the header/notes/MR layout and the blur-save wiring twice.
- **Independent model classes.** Models should live in one class (GoldrynModels.tsx) and individual components should pull them in separately.
- **No routing.** Single-user, desktop-first, no requirement to deep-link or bookmark a specific item — plain React state is sufficient and avoids pulling in React Router for no real benefit.
- **Popup is dumb on purpose.** Given save-on-blur already commits each field independently, there's no meaningful "form state" to preserve on error — the field itself still holds whatever the user typed, so the toast only needs to report success/failure, not manage recovery.

## Open considerations

- **Overlapping parallelogram cards.** Deferred to a later phase (tentatively Phase 3, alongside search) — true overlap needs hand-tuned responsive positioning that's a separate effort from the base clipped-corner shape shipped in Phase 1.
- **Mobile view.** Explicit stretch goal, not designed against for Phase 1. Revisit once the desktop layout is stable.
- **Save indicators beyond the toast.** No per-field spinner/checkmark planned for Phase 1; the top-of-page toast is the only save feedback. Could add finer-grained indicators later if the toast feels insufficient in practice.
- **URL routing.** Explicitly rejected for now; flag for reconsideration only if multi-device/bookmarking needs emerge later.
