// Numeric field parsing. Each returns `null` for an empty field (clears the value)
// and `undefined` when the input is invalid and shouldn't be sent at all.

/** "" -> null, "$1,200.50" -> 1200.5, "abc" / "-5" -> undefined */
export function parseCost(raw: string): number | null | undefined {
  const cleaned = raw.trim().replace(/^\$/, '').replace(/,/g, '')
  if (cleaned === '') return null
  const value = Number(cleaned)
  return Number.isFinite(value) && value >= 0 ? value : undefined
}

/** "" -> null, "90" -> 90, "1.5" / "0" / "abc" -> undefined */
export function parseCadence(raw: string): number | null | undefined {
  const cleaned = raw.trim()
  if (cleaned === '') return null
  const value = Number(cleaned)
  return Number.isInteger(value) && value >= 1 ? value : undefined
}

/** Free-text fields: blank becomes null so the column is cleared rather than set to "". */
export function blankToNull(raw: string): string | null {
  return raw.trim() === '' ? null : raw
}
