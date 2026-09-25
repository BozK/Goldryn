import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { motion } from 'motion/react'
import type { Item, ItemDetail, ItemPatch, MaintenanceRecord, Note } from '../lib/GoldrynModels'
import { api, ApiError } from '../api/client'
import { formatDay, formatTimestamp } from '../lib/dates'
import { isAuthFailure, rejectInvalid } from '../lib/feedback'
import type { Mutate } from '../lib/feedback'
import { resolveColor } from '../palette'
import { blankToNull, parseCadence } from '../parse'
import { useCreateThenUpdate } from '../useCreateThenUpdate'
import { ColorPicker } from './ColorPicker'
import { EditableField } from './EditableField'
import { NoteCard } from './NoteCard'
import { RecordCard } from './RecordCard'

export type PanelEntry = 'left' | 'right'

interface ItemPanelProps {
  /** null => "new" mode. Flips to the created id after the first save. */
  itemId: number | null
  /** New items slide in from the left, existing ones from the right. */
  enterFrom: PanelEntry
  mutate: Mutate
  onCreated: (id: number) => void
  onClose: () => void
  onUnauthorized: () => void
}

type LoadState = { status: 'loading' } | { status: 'ready'; detail: ItemDetail | null } | { status: 'failed' }

export function ItemPanel({ itemId, enterFrom, mutate, onCreated, onClose, onUnauthorized }: ItemPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const offscreen = enterFrom === 'left' ? '-100%' : '100%'

  // Loaded once per opening: the panel stays mounted when a new item gets its id,
  // so that change must not trigger a reload over what the user is typing.
  const [openedWithId] = useState(itemId)
  const [load, setLoad] = useState<LoadState>(
    openedWithId === null ? { status: 'ready', detail: null } : { status: 'loading' },
  )

  useEffect(() => {
    if (openedWithId === null) return
    let cancelled = false
    api
      .getItem(openedWithId)
      .then((detail) => !cancelled && setLoad({ status: 'ready', detail }))
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && isAuthFailure(err.status)) onUnauthorized()
        else setLoad({ status: 'failed' })
      })
    return () => {
      cancelled = true
    }
  }, [openedWithId, onUnauthorized])

  useEffect(() => {
    // Escape doesn't move focus by itself, so blur first to flush any in-progress edit.
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
      onClose()
    }

    // A plain `click` (never a preventDefault'd mousedown), so the field's blur-save
    // has already fired by the time we close. Cards and the + control opt out via
    // data-keep-panel-open: they switch the panel instead of closing it.
    const handleClick = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element) || !target.isConnected) return
      if (panelRef.current?.contains(target)) return
      if (target.closest('[data-keep-panel-open]')) return
      onClose()
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('click', handleClick)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('click', handleClick)
    }
  }, [onClose])

  return (
    <motion.aside
      ref={panelRef}
      initial={{ x: offscreen }}
      animate={{ x: 0 }}
      exit={{ x: offscreen }}
      transition={{ type: 'spring', stiffness: 320, damping: 36 }}
      className="absolute inset-y-0 right-0 z-10 w-3/5 overflow-y-auto border-l border-surface-line bg-surface-raised shadow-2xl"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute top-4 right-4 z-10 rounded-full px-3 py-1 text-2xl leading-none text-white/70 hover:bg-white/10 hover:text-white"
      >
        ×
      </button>

      {load.status === 'loading' && <p className="p-8 text-white/50">Loading...</p>}
      {load.status === 'failed' && <p className="p-8 text-red-300">Couldn't load this item.</p>}
      {load.status === 'ready' && (
        <ItemPanelContent initial={load.detail} mutate={mutate} onCreated={onCreated} onArchived={onClose} />
      )}
    </motion.aside>
  )
}

// ============================================================================
// Panel contents (mounted once the item is loaded, or immediately in new mode)
// ============================================================================

interface Entry<T> {
  /** Stable React key, kept when a draft is saved so the card never remounts mid-edit. */
  key: string
  initial: T | null
}

let draftCounter = 0
const draftKey = () => `draft-${++draftCounter}`

function toItem({ notes: _notes, maintenance_records: _records, ...item }: ItemDetail): Item {
  return item
}

function noteEntries(notes: Note[]): Entry<Note>[] {
  return [...notes]
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id)
    .map((note) => ({ key: `note-${note.id}`, initial: note }))
}

function recordEntries(records: MaintenanceRecord[]): Entry<MaintenanceRecord>[] {
  return [...records]
    .sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id)
    .map((record) => ({ key: `record-${record.id}`, initial: record }))
}

interface ItemPanelContentProps {
  initial: ItemDetail | null
  mutate: Mutate
  onCreated: (id: number) => void
  onArchived: () => void
}

function ItemPanelContent({ initial, mutate, onCreated, onArchived }: ItemPanelContentProps) {
  const header = useCreateThenUpdate<Item, ItemPatch>({
    initial: initial && toItem(initial),
    canCreate: (pending) => Boolean(pending.name?.trim()),
    create: (pending) => mutate(() => api.createItem({ ...pending, name: pending.name ?? '' })),
    update: (id, patch) => mutate(() => api.updateItem(id, patch)),
    onCreated: (item) => onCreated(item.id),
  })
  const item = header.saved
  const isNew = item === null

  // Tracked locally so a color picked before the item exists still shows.
  const [color, setColor] = useState(initial?.color ?? null)
  const { bg, accent } = resolveColor(color)

  const [notes, setNotes] = useState(() => noteEntries(initial?.notes ?? []))
  const [records, setRecords] = useState(() => recordEntries(initial?.maintenance_records ?? []))

  // Record changes can move next_due, which only the server computes.
  const refreshHeader = async () => {
    if (!item) return
    try {
      header.replace(toItem(await api.getItem(item.id)))
    } catch {
      // Only next_due is stale; the landing grid's refetch still picks it up.
    }
  }

  const saveCadence = (raw: string) => {
    const cadence = parseCadence(raw)
    if (cadence === undefined) {
      void mutate(() => rejectInvalid('Cadence must be a whole number of days'))
      return
    }
    void header.save({ cadence_days: cadence })
  }

  const pickColor = (next: string) => {
    setColor(next)
    void header.save({ color: next })
  }

  const archive = async () => {
    if (!item || !window.confirm(`Archive "${item.name}"? It will disappear from the list.`)) return
    if (await mutate(() => api.deleteItem(item.id))) onArchived()
  }

  return (
    <>
      <header className="space-y-4 px-8 pt-8 pb-6" style={{ backgroundColor: bg }}>
        <div className="pr-12">
          <EditableField
            value={item?.name ?? ''}
            onCommit={(name) => void header.save({ name: name.trim() })}
            label="Name"
            placeholder="Name this item"
            autoFocus={isNew}
            className="text-3xl font-bold"
          />
          {item && (
            <p className="mt-1 text-sm text-white/65">
              Created {formatTimestamp(item.created_at)}
              {item.next_due && <> · Next due {formatDay(item.next_due)}</>}
            </p>
          )}
        </div>

        <dl className="grid grid-cols-[9rem_1fr] items-start gap-x-4 gap-y-3 text-sm">
          <dt className="pt-1.5 text-white/65">Color</dt>
          <dd>
            <ColorPicker value={color} onChange={pickColor} />
          </dd>

          <dt className="pt-1 text-white/65">Cadence</dt>
          <dd>
            <EditableField
              value={item?.cadence_days?.toString() ?? ''}
              onCommit={saveCadence}
              label="Cadence in days"
              placeholder="Cadence in days (optional)"
              inputMode="numeric"
              display={(days) => `Every ${days} day${days === '1' ? '' : 's'}`}
            />
          </dd>

          <dt className="pt-1 text-white/65">Next maintenance</dt>
          <dd>
            <EditableField
              value={item?.next_maintenance_notes ?? ''}
              onCommit={(text) => void header.save({ next_maintenance_notes: blankToNull(text) })}
              label="Next maintenance notes"
              placeholder="Anything to remember for next time"
              multiline
            />
          </dd>
        </dl>

        {item && (
          <div className="flex justify-end">
            <button type="button" onClick={archive} className="text-sm text-white/60 hover:text-red-300">
              Archive item
            </button>
          </div>
        )}
      </header>

      <PanelSection
        title="Notes"
        canAdd={!isNew}
        onAdd={() => setNotes((current) => [{ key: draftKey(), initial: null }, ...current])}
      >
        {item &&
          notes.map((entry) => (
            <NoteCard
              key={entry.key}
              itemId={item.id}
              initial={entry.initial}
              accent={accent}
              mutate={mutate}
              onRemove={() => setNotes((current) => current.filter((e) => e.key !== entry.key))}
            />
          ))}
      </PanelSection>

      <PanelSection
        title="Maintenance records"
        canAdd={!isNew}
        onAdd={() => setRecords((current) => [{ key: draftKey(), initial: null }, ...current])}
      >
        {item &&
          records.map((entry) => (
            <RecordCard
              key={entry.key}
              itemId={item.id}
              initial={entry.initial}
              accent={accent}
              mutate={mutate}
              onSaved={refreshHeader}
              onRemove={() => setRecords((current) => current.filter((e) => e.key !== entry.key))}
            />
          ))}
      </PanelSection>
    </>
  )
}

interface PanelSectionProps {
  title: string
  canAdd: boolean
  onAdd: () => void
  children: ReactNode
}

function PanelSection({ title, canAdd, onAdd, children }: PanelSectionProps) {
  return (
    <section className="px-8 py-6">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button
          type="button"
          onClick={onAdd}
          disabled={!canAdd}
          title={canAdd ? undefined : 'Name the item first'}
          className="rounded-md px-2 py-1 text-sm text-gold hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-transparent"
        >
          + Add New
        </button>
      </div>
      <div className="grid grid-cols-2 items-start gap-3">{children}</div>
    </section>
  )
}
