import type { Note, NotePatch } from '../lib/GoldrynModels'
import { api } from '../api/client'
import { formatTimestamp } from '../lib/dates'
import type { Mutate } from '../lib/feedback'
import { useCreateThenUpdate } from '../useCreateThenUpdate'
import { EditableField } from './EditableField'

interface NoteCardProps {
  itemId: number
  /** null for a draft created by "+ Add New". */
  initial: Note | null
  accent: string
  mutate: Mutate
  /** Removes this card from the list (after a delete, or when a draft is abandoned). */
  onRemove: () => void
}

export function NoteCard({ itemId, initial, accent, mutate, onRemove }: NoteCardProps) {
  const note = useCreateThenUpdate<Note, NotePatch>({
    initial,
    canCreate: (pending) => Boolean(pending.body?.trim()),
    create: (pending) => mutate(() => api.createNote(itemId, { body: pending.body ?? '' })),
    update: (id, patch) => mutate(() => api.updateNote(id, patch)),
  })
  const saved = note.saved

  const handleDelete = async () => {
    if (saved === null) {
      onRemove()
      return
    }
    if (!window.confirm('Delete this note?')) return
    if (await mutate(() => api.deleteNote(saved.id))) onRemove()
  }

  // EditableField's box bleeds 0.5rem left and right but not vertically, so the top padding is
  // 0.5rem less than the left: an open field then sits evenly inset. The × is centered on the first field.
  return (
    <div
      className="group relative clip-corners clip-cut-4 pt-2.5 pr-12 pb-4 pl-4.5"
      style={{ backgroundColor: accent }}
    >
      <EditableField
        value={saved?.body ?? ''}
        onCommit={(body) => void note.save({ body })}
        onBlurUnchanged={saved === null ? onRemove : undefined}
        label="Note"
        placeholder="Write a note..."
        multiline
        autoFocus={saved === null}
      />
      {saved && <p className="mt-2 text-xs text-white/65">{formatTimestamp(saved.created_at)}</p>}
      <button
        type="button"
        onClick={handleDelete}
        aria-label="Delete note"
        title="Delete note"
        className="absolute top-3.5 right-2.5 flex size-6 items-center justify-center rounded text-white/60 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/20 hover:text-white focus:opacity-100"
      >
        ×
      </button>
    </div>
  )
}
