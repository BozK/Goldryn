import type {
  Attachment,
  AttachmentPatch,
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
  TagSummary,
} from '../lib/GoldrynModels'

/**
 * Thrown for any failed request. `status` is the HTTP status, or 0 when the
 * server couldn't be reached at all (treated like a 5xx by callers).
 * `retryAfter` is the Retry-After header in seconds, when a 429 sends one.
 */
export class ApiError extends Error {
  status: number
  retryAfter?: number

  constructor(status: number, message: string, retryAfter?: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

/** `body` is sent as JSON, except FormData, which the browser encodes as multipart itself. */
async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const isJson = body !== undefined && !(body instanceof FormData)
  let response: Response
  try {
    response = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: isJson ? { 'Content-Type': 'application/json' } : undefined,
      body: isJson ? JSON.stringify(body) : (body as FormData | undefined),
    })
  } catch {
    throw new ApiError(0, 'Unable to reach the server')
  }

  if (!response.ok) {
    const retryAfter = Number(response.headers.get('Retry-After')) || undefined
    throw new ApiError(response.status, `${method} ${path} failed with ${response.status}`, retryAfter)
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

  // -------- Tags --------
  listTags: () => request<TagSummary[]>('GET', '/api/tags'),

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

  // -------- Attachments --------
  uploadAttachment: (itemId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Attachment>('POST', `/api/items/${itemId}/attachments`, form)
  },
  updateAttachment: (id: number, patch: AttachmentPatch) =>
    request<Attachment>('PATCH', `/api/attachments/${id}`, patch),
  /** Archives it: the server keeps the file but stops listing or serving it. */
  deleteAttachment: (id: number) => request<MessageResponse>('DELETE', `/api/attachments/${id}`),
}

/** Plain URLs for links and <img>, not fetched through `request`. */
export const attachmentUrls = {
  content: (id: number) => `/api/attachments/${id}/content`,
  preview: (id: number) => `/api/attachments/${id}/preview`,
}
