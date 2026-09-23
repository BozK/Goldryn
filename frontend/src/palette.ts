// The backend stores a generic color name (e.g. "Green"); the frontend owns what
// that name looks like. `bg` is the darker shade (cards, panel header), `accent`
// the lighter one (note / maintenance record wrappers). Text is white on both.

export interface PaletteEntry {
  bg: string
  accent: string
}

export const PALETTE: Record<string, PaletteEntry> = {
  Green: { bg: '#1b4332', accent: '#40916c' },
  Blue: { bg: '#1e3a5f', accent: '#4a7fb5' },
  Teal: { bg: '#134e4a', accent: '#2a9d8f' },
  Purple: { bg: '#3c1f5c', accent: '#7b52ab' },
  Pink: { bg: '#5c1a3f', accent: '#b0487f' },
  Red: { bg: '#641a1a', accent: '#b54545' },
  Orange: { bg: '#6b3410', accent: '#c26a2e' },
  Gold: { bg: '#5c4510', accent: '#b8912e' },
  Brown: { bg: '#4a3222', accent: '#8c6446' },
  Slate: { bg: '#2c333d', accent: '#5b6675' },
}

export const COLOR_NAMES = Object.keys(PALETTE)

const FALLBACK = PALETTE.Slate

/** Resolve a stored color name to its shades; unknown or missing names fall back to Slate. */
export function resolveColor(color: string | null | undefined): PaletteEntry {
  return (color && PALETTE[color]) || FALLBACK
}
