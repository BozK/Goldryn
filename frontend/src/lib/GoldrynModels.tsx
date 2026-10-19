// API models shared across components. Shapes mirror BACKEND_DESIGN.md.
// Dates are "YYYY-MM-DD"; timestamps are ISO-8601 UTC ("2026-01-04T12:00:00Z").

// ============================================================================
// Auth
// ============================================================================

export interface LoginRequest {
  username: string
  password: string
}

export interface Me {
  username: string
}

// ============================================================================
// Items
// ============================================================================

/** One row of GET /api/items. */
export interface ItemSummary {
  id: number
  name: string
  color: string | null
  cadence_days: number | null
  next_due: string | null
}

/** Item header fields, returned by POST/PATCH /api/items. */
export interface Item {
  id: number
  name: string
  color: string | null
  cadence_days: number | null
  next_maintenance_notes: string | null
  created_at: string
  next_due: string | null
  /** Lowercase, in the order they were added; at most 3. */
  tags: string[]
}

/** GET /api/items/{id}: the item plus all of its children. */
export interface ItemDetail extends Item {
  notes: Note[]
  maintenance_records: MaintenanceRecord[]
}

export interface ItemCreate {
  name: string
  color?: string | null
  cadence_days?: number | null
  next_maintenance_notes?: string | null
  /** Replaces the whole set. The server lowercases, de-duplicates and creates any new tag. */
  tags?: string[]
}

export type ItemPatch = Partial<ItemCreate>

// ============================================================================
// Tags
// ============================================================================

/** One row of GET /api/tags: a tag at least one active item uses, most-used first. */
export interface TagSummary {
  name: string
  item_count: number
}

// ============================================================================
// Notes
// ============================================================================

export interface Note {
  id: number
  body: string
  created_at: string
}

export interface NoteCreate {
  body: string
}

export type NotePatch = Partial<NoteCreate>

// ============================================================================
// Maintenance Records
// ============================================================================

export interface MaintenanceRecord {
  id: number
  date: string
  summary: string | null
  cost: number | null
  contractor_info: string | null
}

export interface MaintenanceRecordCreate {
  date: string
  summary?: string | null
  cost?: number | null
  contractor_info?: string | null
}

export type MaintenanceRecordPatch = Partial<MaintenanceRecordCreate>

// ============================================================================
// Generic
// ============================================================================

export interface MessageResponse {
  message: string
}
