import { useEffect, useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { TagSummary } from '../lib/GoldrynModels'
import { MAX_TAG_LENGTH, MAX_TAGS, normalizeTag, suggestTags } from '../lib/tags'

interface TagInputProps {
  /** The item's saved tags, or null while the item is still a draft (it must exist to be tagged). */
  saved: string[] | null
  /** Every tag in use, most-used first, for the dropdown. */
  suggestions: TagSummary[]
  accent: string
  /** Saves the whole list. Resolves false if the save failed (the failure is already toasted). */
  onSave: (tags: string[]) => Promise<boolean>
}

/**
 * Tag chips plus a type-ahead input. See TAGS_PHASE1.md for the full behavior.
 *
 * Chips update as soon as a tag is added or removed. Each change sends the full
 * list, so saves run one at a time: out of order, an older list could land last.
 * A failed save puts back the last saved list.
 */
export function TagInput({ saved, suggestions, accent, onSave }: TagInputProps) {
  const [tags, setTags] = useState<string[]>(saved ?? [])
  const [lastSaved, setLastSaved] = useState(saved)
  const [pendingSaves, setPendingSaves] = useState(0)
  const savedRef = useRef(saved)
  const queue = useRef<Promise<void>>(Promise.resolve())

  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  // -1 = nothing highlighted: Enter adds the typed text.
  const [highlight, setHighlight] = useState(-1)
  const listId = useId()

  useEffect(() => {
    savedRef.current = saved
  }, [saved])

  // Any header save returns the item's tags. Take them, unless a tag save is still
  // on its way: then the chips are newer than what came back.
  if (saved !== lastSaved) {
    setLastSaved(saved)
    if (pendingSaves === 0) setTags(saved ?? [])
  }

  const commit = (next: string[]) => {
    setTags(next)
    setPendingSaves((count) => count + 1)
    queue.current = queue.current.then(async () => {
      if (!(await onSave(next))) setTags(savedRef.current ?? [])
      setPendingSaves((count) => count - 1)
    })
  }

  const add = (raw: string) => {
    const name = normalizeTag(raw)
    setQuery('')
    setHighlight(-1)
    if (!name || tags.includes(name) || tags.length >= MAX_TAGS) return
    commit([...tags, name])
  }

  const remove = (name: string) => commit(tags.filter((tag) => tag !== name))

  const typed = normalizeTag(query)
  const matches = suggestTags(suggestions, query, tags)
  const isNewTag = typed !== '' && !tags.includes(typed) && !suggestions.some((tag) => tag.name === typed)
  const options = isNewTag ? [...matches, typed] : matches
  const showList = isOpen && options.length > 0

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (options.length === 0) return
      event.preventDefault()
      setIsOpen(true)
      // Cycles through -1 (the typed text) and every option.
      const next = highlight + (event.key === 'ArrowDown' ? 1 : -1)
      setHighlight(next >= options.length ? -1 : next < -1 ? options.length - 1 : next)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      add(highlight >= 0 ? options[highlight] : query)
    } else if (event.key === 'Escape' && showList) {
      // Close the dropdown only. A second Escape reaches the panel, which saves and closes.
      event.stopPropagation()
      setIsOpen(false)
      setHighlight(-1)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {tags.length > 0 && (
        <ul className="contents">
          {tags.map((name) => (
            <li
              key={name}
              className="flex items-center gap-1 clip-corners clip-cut-2 clip-round-1 py-1 pr-2.5 pl-3 text-sm"
              style={{ backgroundColor: accent }}
            >
              {name}
              <button
                type="button"
                onClick={() => remove(name)}
                aria-label={`Remove tag ${name}`}
                title="Remove tag"
                className="rounded px-1 leading-none text-white/70 hover:bg-black/20 hover:text-white"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}

      {tags.length >= MAX_TAGS ? (
        <span className="text-xs text-white/45">{MAX_TAGS} tags max</span>
      ) : (
        <div className="relative">
          <input
            role="combobox"
            aria-label="Add a tag"
            aria-expanded={showList}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={showList && highlight >= 0 ? `${listId}-${highlight}` : undefined}
            placeholder={saved === null ? 'Name the item first' : 'Add a tag'}
            disabled={saved === null}
            value={query}
            maxLength={MAX_TAG_LENGTH}
            onChange={(event) => {
              setQuery(event.target.value)
              setHighlight(-1)
              setIsOpen(true)
            }}
            onFocus={() => setIsOpen(true)}
            // Blur is the commit, as for every other field: whatever was typed becomes a tag.
            onBlur={() => {
              setIsOpen(false)
              add(query)
            }}
            onKeyDown={handleKeyDown}
            className="w-40 rounded-md bg-black/25 px-2 py-1 placeholder-white/45 ring-1 ring-white/20 outline-none focus:ring-gold disabled:cursor-not-allowed disabled:opacity-50"
          />

          {showList && (
            <ul
              id={listId}
              role="listbox"
              className="absolute top-full left-0 z-20 mt-1 max-h-64 w-max max-w-64 min-w-full overflow-y-auto rounded-md bg-surface-raised py-1 text-sm shadow-xl ring-1 ring-surface-line"
            >
              {options.map((name, index) => (
                <li
                  key={name}
                  id={`${listId}-${index}`}
                  role="option"
                  aria-selected={index === highlight}
                  // Keep focus in the input, so picking a row doesn't blur-save the typed text first.
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => add(name)}
                  onMouseEnter={() => setHighlight(index)}
                  className={`cursor-pointer truncate px-3 py-1.5 ${index === highlight ? 'bg-white/10' : ''}`}
                >
                  {isNewTag && index === options.length - 1 ? `Create "${name}"` : name}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
