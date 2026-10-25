// The backend stores a generic color name (e.g. "Green"); the frontend owns what
// that name looks like. `bg` is the darker shade (cards, panel header), `accent`
// the lighter one (note / maintenance record wrappers). Text is white on both.

export interface PaletteEntry {
  bg: string
  accent: string
}

// Insertion order is the picker's order: around the hue wheel, then the earthy and grey ones.
// Names are stored on items, so never rename or remove one; shades can be retuned freely.
export const PALETTE: Record<string, PaletteEntry> = {
  Red: { bg: '#641a1a', accent: '#b54545' },
  Rust: { bg: '#5e2a12', accent: '#b0582c' },
  Orange: { bg: '#6b3410', accent: '#c26a2e' },
  Gold: { bg: '#5c4510', accent: '#ab8628' },
  Olive: { bg: '#3f4214', accent: '#878a2e' },
  Moss: { bg: '#26401a', accent: '#5a8a3a' },
  Green: { bg: '#1b4332', accent: '#40916c' },
  Teal: { bg: '#134e4a', accent: '#2a9d8f' },
  Sky: { bg: '#0a466e', accent: '#1f8fc9' },
  Blue: { bg: '#1e3a5f', accent: '#4a7fb5' },
  Indigo: { bg: '#262a66', accent: '#5560c0' },
  Purple: { bg: '#3c1f5c', accent: '#7b52ab' },
  Plum: { bg: '#4d1a52', accent: '#9a4aa3' },
  Pink: { bg: '#5c1a3f', accent: '#b0487f' },
  Crimson: { bg: '#5a0f24', accent: '#c22d55' },
  Brown: { bg: '#4a3222', accent: '#8c6446' },
  Sand: { bg: '#4f4430', accent: '#9a8660' },
  Sage: { bg: '#2f3b33', accent: '#687c6c' },
  Slate: { bg: '#2c333d', accent: '#5b6675' },
  Charcoal: { bg: '#232323', accent: '#525252' },
}

export const COLOR_NAMES = Object.keys(PALETTE)

const FALLBACK = PALETTE.Slate

/** Resolve a stored color name to its shades; unknown or missing names fall back to Slate. */
export function resolveColor(color: string | null | undefined): PaletteEntry {
  return (color && PALETTE[color]) || FALLBACK
}
