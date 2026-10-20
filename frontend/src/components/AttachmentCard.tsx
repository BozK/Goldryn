import type { Attachment } from '../lib/GoldrynModels'
import { api, attachmentUrls } from '../api/client'
import { formatSize, opensInTab, typeLabel } from '../lib/attachments'
import { formatTimestamp } from '../lib/dates'
import type { Mutate } from '../lib/feedback'
import { EditableField } from './EditableField'

interface AttachmentCardProps {
  attachment: Attachment
  accent: string
  mutate: Mutate
  /** Replaces this attachment in the list with the server's copy after a rename. */
  onChange: (next: Attachment) => void
  onRemove: () => void
}

/**
 * One file on the item. Images show their preview; anything else shows a type badge.
 * The name is click-to-edit like every other field, so opening the file goes through
 * the preview, the badge, or the Open/Download link instead.
 */
export function AttachmentCard({ attachment, accent, mutate, onChange, onRemove }: AttachmentCardProps) {
  const { id, filename, kind } = attachment
  const isImage = kind === 'image'
  const href = attachmentUrls.content(id)
  // The server sends a `file` as a download whatever the link says; `download` just
  // keeps the browser from opening a blank tab first.
  const linkProps = opensInTab(kind)
    ? { href, target: '_blank', rel: 'noopener noreferrer', title: `Open ${filename}` }
    : { href, download: filename, title: `Download ${filename}` }

  const rename = async (next: string) => {
    const updated = await mutate(() => api.updateAttachment(id, { filename: next.trim() }))
    if (updated) onChange(updated)
  }

  const handleDelete = async () => {
    if (!window.confirm(`Remove "${filename}" from this item?`)) return
    if (await mutate(() => api.deleteAttachment(id))) onRemove()
  }

  const details = [
    isImage && typeLabel(filename),
    formatSize(attachment.size_bytes),
    formatTimestamp(attachment.created_at),
  ].filter(Boolean)

  return (
    <div className="group relative clip-corners clip-cut-4" style={{ backgroundColor: accent }}>
      {isImage && (
        <a {...linkProps} className="block bg-black/20">
          <img
            src={attachmentUrls.preview(id)}
            alt={filename}
            loading="lazy"
            className="max-h-80 w-full object-cover object-top"
          />
        </a>
      )}

      {/* Same insets as notes and records, so the name lines up with their text. */}
      <div className="flex items-start gap-3 pt-2.5 pr-12 pb-3 pl-4.5">
        {!isImage && (
          <a
            {...linkProps}
            className="mt-0.5 flex h-12 w-10 shrink-0 items-center justify-center rounded bg-black/25 text-[0.625rem] font-bold tracking-wide hover:bg-black/40"
          >
            {typeLabel(filename)}
          </a>
        )}
        <div className="min-w-0 flex-1">
          <EditableField value={filename} onCommit={rename} label="File name" placeholder="File name" />
          {/* On a narrow card the link drops to its own line rather than splitting the details. */}
          <p className="mt-1 flex flex-wrap justify-between gap-x-3 text-xs whitespace-nowrap text-white/65">
            <span>{details.join(' · ')}</span>
            <a {...linkProps} className="hover:text-white hover:underline">
              {opensInTab(kind) ? 'Open ↗' : 'Download'}
            </a>
          </p>
        </div>
      </div>

      <button
        type="button"
        onClick={handleDelete}
        aria-label="Remove attachment"
        title="Remove attachment"
        className={`absolute right-2.5 flex size-6 items-center justify-center rounded text-white/60 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-black/20 hover:text-white focus:opacity-100 ${
          isImage ? 'top-2.5 bg-black/40' : 'top-3.5'
        }`}
      >
        ×
      </button>
    </div>
  )
}

/** Stands in for a file while it uploads. */
export function UploadingCard({ filename, accent }: { filename: string; accent: string }) {
  return (
    <div
      className="clip-corners clip-cut-4 animate-pulse px-4.5 py-3 text-sm text-white/70"
      style={{ backgroundColor: accent }}
    >
      <p className="truncate">Uploading {filename}…</p>
    </div>
  )
}
