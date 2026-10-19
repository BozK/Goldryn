// Tag input helpers. Normalization mirrors the backend's (GoldrynModels.py), so the
// input can tell "already on this item" and "already exists" without a request.

import type { TagSummary } from './GoldrynModels'

export const MAX_TAGS = 3
export const MAX_TAG_LENGTH = 32
const MAX_SUGGESTIONS = 8

/** "  Water   Heater " -> "water heater": one spelling per tag. */
export function normalizeTag(raw: string): string {
  return raw.trim().split(/\s+/).join(' ').toLowerCase()
}

/**
 * Suggestions for the typed text, leaving out tags already on the item. Names that
 * start with the text come before names that only contain it; each group keeps the
 * server's most-used-first order. With nothing typed, the most-used tags.
 */
export function suggestTags(all: TagSummary[], typed: string, exclude: string[]): string[] {
  const query = normalizeTag(typed)
  const available = all.map((tag) => tag.name).filter((name) => !exclude.includes(name))
  if (!query) return available.slice(0, MAX_SUGGESTIONS)

  const prefix = available.filter((name) => name.startsWith(query))
  const contains = available.filter((name) => !name.startsWith(query) && name.includes(query))
  return [...prefix, ...contains].slice(0, MAX_SUGGESTIONS)
}
