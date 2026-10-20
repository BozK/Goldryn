import type { MaintenanceRecord, MaintenanceRecordCreate, MaintenanceRecordPatch } from '../lib/GoldrynModels'
import { api } from '../api/client'
import { formatDay, todayYmd } from '../lib/dates'
import { rejectInvalid } from '../lib/feedback'
import type { Mutate } from '../lib/feedback'
import { blankToNull, parseCost } from '../parse'
import { useCreateThenUpdate } from '../useCreateThenUpdate'
import { EditableField } from './EditableField'

interface RecordCardProps {
  itemId: number
  /** null for a draft created by "+ Add New". */
  initial: MaintenanceRecord | null
  accent: string
  mutate: Mutate
  /** Any saved change can move the item's next_due, so the panel re-reads it. */
  onSaved: () => void
  onRemove: () => void
}

function formatCost(raw: string): string {
  const value = parseCost(raw)
  return typeof value === 'number' ? value.toLocaleString(undefined, { style: 'currency', currency: 'USD' }) : raw
}

export function RecordCard({ itemId, initial, accent, mutate, onSaved, onRemove }: RecordCardProps) {
  // Drafts start dated today: `date` is NOT NULL, so every POST needs one.
  const draftDate = todayYmd()
  const record = useCreateThenUpdate<MaintenanceRecord, MaintenanceRecordPatch>({
    initial,
    initialPending: { date: draftDate },
    canCreate: () => true,
    create: (pending) =>
      mutate(() => api.createRecord(itemId, { date: draftDate, ...pending } as MaintenanceRecordCreate)),
    update: (id, patch) => mutate(() => api.updateRecord(id, patch)),
  })
  const saved = record.saved

  const save = async (patch: MaintenanceRecordPatch) => {
    if (await record.save(patch)) onSaved()
  }

  const saveCost = (raw: string) => {
    const cost = parseCost(raw)
    if (cost === undefined) {
      void mutate(() => rejectInvalid('Cost must be a non-negative number'))
      return
    }
    void save({ cost })
  }

  const handleDelete = async () => {
    if (saved === null) {
      onRemove()
      return
    }
    if (!window.confirm('Delete this maintenance record?')) return
    if (await mutate(() => api.deleteRecord(saved.id))) {
      onRemove()
      onSaved()
    }
  }

  // EditableField's box bleeds 0.5rem left and right but not vertically, so the top padding is
  // 0.5rem less than the left: an open field then sits evenly inset. The × is centered on the first field.
  return (
    <div
      className="group relative clip-corners clip-cut-4 space-y-1 py-2.5 pr-12 pl-4.5"
      style={{ backgroundColor: accent }}
    >
      <EditableField
        value={saved?.date ?? draftDate}
        onCommit={(date) => void save({ date })}
        label="Date"
        placeholder="Date"
        type="date"
        display={formatDay}
        className="text-sm font-semibold"
      />
      <EditableField
        value={saved?.summary ?? ''}
        onCommit={(summary) => void save({ summary: blankToNull(summary) })}
        label="Summary"
        placeholder="What was done?"
        multiline
        autoFocus={saved === null}
      />
      <EditableField
        value={saved?.cost?.toString() ?? ''}
        onCommit={saveCost}
        label="Cost"
        placeholder="Cost"
        inputMode="decimal"
        display={formatCost}
        className="text-sm"
      />
      <EditableField
        value={saved?.contractor_info ?? ''}
        onCommit={(info) => void save({ contractor_info: blankToNull(info) })}
        label="Contractor"
        placeholder="Contractor (name, phone, website...)"
        multiline
        className="text-sm text-white/85"
      />
      <button
        type="button"
        onClick={handleDelete}
        aria-label="Delete maintenance record"
        title="Delete maintenance record"
        className="absolute top-3 right-2.5 flex size-6 items-center justify-center rounded text-white/60 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/20 hover:text-white focus:opacity-100"
      >
        ×
      </button>
    </div>
  )
}
