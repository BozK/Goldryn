import type {
  Item,
  ItemCreate,
  ItemDetail,
  ItemPatch,
  ItemSummary,
  LoginRequest,
  MaintenanceRecord,
  MaintenanceRecordCreate,
  MaintenanceRecordPatch,
  Me,
  MessageResponse,
  Note,
  NoteCreate,
  NotePatch,
} from '../lib/GoldrynModels'

/**
 * Thrown for any failed request. `status` is the HTTP status, or 0 when the
 * server couldn't be reached at all (treated like a 5xx by callers).
 */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Unable to reach the server')
  }

  if (!response.ok) {
    throw new ApiError(response.status, `${method} ${path} failed with ${response.status}`)
  }

  try {
    return (await response.json()) as T
  } catch {
    throw new ApiError(500, `${method} ${path} returned an invalid response`)
  }
}

export const api = {
  // -------- Auth --------
  login: (credentials: LoginRequest) => request<Me>('POST', '/api/auth/login', credentials),
  logout: () => request<MessageResponse>('POST', '/api/auth/logout'),
  me: () => request<Me>('GET', '/api/me'),

  // -------- Items --------
  listItems: () => request<ItemSummary[]>('GET', '/api/items'),
  getItem: (id: number) => request<ItemDetail>('GET', `/api/items/${id}`),
  createItem: (item: ItemCreate) => request<Item>('POST', '/api/items', item),
  updateItem: (id: number, patch: ItemPatch) => request<Item>('PATCH', `/api/items/${id}`, patch),
  deleteItem: (id: number) => request<MessageResponse>('DELETE', `/api/items/${id}`),

  // -------- Notes --------
  createNote: (itemId: number, note: NoteCreate) => request<Note>('POST', `/api/items/${itemId}/notes`, note),
  updateNote: (id: number, patch: NotePatch) => request<Note>('PATCH', `/api/notes/${id}`, patch),
  deleteNote: (id: number) => request<MessageResponse>('DELETE', `/api/notes/${id}`),

  // -------- Maintenance Records --------
  createRecord: (itemId: number, record: MaintenanceRecordCreate) =>
    request<MaintenanceRecord>('POST', `/api/items/${itemId}/maintenance_records`, record),
  updateRecord: (id: number, patch: MaintenanceRecordPatch) =>
    request<MaintenanceRecord>('PATCH', `/api/maintenance_records/${id}`, patch),
  deleteRecord: (id: number) => request<MessageResponse>('DELETE', `/api/maintenance_records/${id}`),
}
