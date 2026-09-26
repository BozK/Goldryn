import { useCallback, useState } from 'react'
import type { FocusEvent, KeyboardEvent } from 'react'

interface EditableFieldProps {
  /** Last saved value ("" for null). */
  value: string
  /** Called on blur, only when the text differs from `value`. */
  onCommit: (next: string) => void
  /** Called on blur when nothing changed, e.g. to discard an empty draft. */
  onBlurUnchanged?: () => void
  label: string
  placeholder: string
  multiline?: boolean
  type?: 'text' | 'date'
  inputMode?: 'text' | 'numeric' | 'decimal'
  /** Formats the value for display mode, e.g. a date or currency. */
  display?: (value: string) => string
  /** Start in edit mode (new item name, fresh drafts). */
  autoFocus?: boolean
  /** Typography shared by display and edit modes so toggling doesn't shift text. */
  className?: string
}

/**
 * Keep-style click-to-edit text: a styled block until focused, then an input that
 * saves on blur. There's no save button anywhere; blur is the commit.
 *
 * The field shows what the user typed, not the last saved value, so a failed save
 * leaves their text in place and the next blur retries it.
 */
export function EditableField({
  value,
  onCommit,
  onBlurUnchanged,
  label,
  placeholder,
  multiline = false,
  type = 'text',
  inputMode,
  display,
  autoFocus = false,
  className = '',
}: EditableFieldProps) {
  const [isEditing, setIsEditing] = useState(autoFocus)
  const [draft, setDraft] = useState(value)
  const [lastValue, setLastValue] = useState(value)

  // A newly saved value replaces the draft, unless the user is mid-edit.
  if (value !== lastValue) {
    setLastValue(value)
    if (!isEditing) setDraft(value)
  }

  const finishEditing = () => {
    setIsEditing(false)
    if (draft !== value) onCommit(draft)
    else onBlurUnchanged?.()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const commits = multiline ? event.key === 'Enter' && (event.ctrlKey || event.metaKey) : event.key === 'Enter'
    if (commits) {
      event.preventDefault()
      event.currentTarget.blur()
    }
  }

  const moveCaretToEnd = (event: FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    if (type === 'date') return
    const end = event.currentTarget.value.length
    event.currentTarget.setSelectionRange(end, end)
  }

  // Focus without scrolling: the panel may still be sliding in, and a scroll-into-view
  // would drag the whole overflow-hidden layout sideways.
  const focusOnMount = useCallback((element: HTMLInputElement | HTMLTextAreaElement | null) => {
    element?.focus({ preventScroll: true })
  }, [])

  const box = `-mx-2 block w-[calc(100%+1rem)] rounded-md px-2 py-1 ${className}`

  if (!isEditing) {
    return (
      <div
        role="button"
        tabIndex={0}
        aria-label={label}
        onFocus={() => setIsEditing(true)}
        className={`${box} cursor-text whitespace-pre-wrap break-words hover:bg-white/10`}
      >
        {draft ? (display?.(draft) ?? draft) : <span className="text-white/45">{placeholder}</span>}
      </div>
    )
  }

  const inputProps = {
    ref: focusOnMount,
    'aria-label': label,
    placeholder,
    value: draft,
    onChange: (event: { target: { value: string } }) => setDraft(event.target.value),
    onBlur: finishEditing,
    onFocus: moveCaretToEnd,
    onKeyDown: handleKeyDown,
    className: `${box} bg-black/25 placeholder-white/45 outline-none ring-1 ring-white/30 focus:ring-gold`,
  }

  return multiline ? (
    <textarea {...inputProps} rows={2} className={`${inputProps.className} field-sizing-content resize-none`} />
  ) : (
    <input {...inputProps} type={type} inputMode={inputMode} />
  )
}
