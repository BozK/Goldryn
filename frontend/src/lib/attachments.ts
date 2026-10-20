// Display helpers for attachments. The server decides each file's kind from its
// contents; nothing here second-guesses it.

import type { AttachmentKind } from './GoldrynModels'

/** Mirrors attachments.MAX_UPLOAD_BYTES on the server, so an oversized file never starts uploading. */
export const MAX_UPLOAD_MB = 50
export const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

const UNITS = ['KB', 'MB', 'GB']

/** 512 -> "512 B", 14_000 -> "14 KB", 2_500_000 -> "2.4 MB" */
export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < UNITS.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${UNITS[unit]}`
}

/** A short type label from the extension, e.g. "PDF" or "DOCX"; "FILE" when there isn't a usable one. */
export function typeLabel(filename: string): string {
  const dot = filename.lastIndexOf('.')
  const extension = dot > 0 ? filename.slice(dot + 1) : ''
  return /^[a-z0-9]{1,5}$/i.test(extension) ? extension.toUpperCase() : 'FILE'
}

/** Images, PDFs and text open in a new tab; anything else downloads. */
export function opensInTab(kind: AttachmentKind): boolean {
  return kind !== 'file'
}

/** Only real file drags, not text or a link dragged from the page. */
export function hasFiles(dataTransfer: DataTransfer | null): boolean {
  return Boolean(dataTransfer?.types.includes('Files'))
}
