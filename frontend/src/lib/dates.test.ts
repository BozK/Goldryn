import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { formatDay, formatTimestamp, isPastDue, todayYmd } from './dates'

describe('formatDay', () => {
  it('formats a YYYY-MM-DD string as a local calendar day', () => {
    expect(formatDay('2026-11-15')).toBe(
      new Date(2026, 10, 15).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      }),
    )
  })

  it('does not shift across the new year', () => {
    expect(formatDay('2026-01-01')).toBe(
      new Date(2026, 0, 1).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      }),
    )
  })
})

describe('formatTimestamp', () => {
  it('formats an ISO timestamp as a local calendar day', () => {
    const iso = '2026-01-04T12:00:00Z'
    expect(formatTimestamp(iso)).toBe(
      new Date(iso).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      }),
    )
  })
})

describe('todayYmd / isPastDue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 5, 15)) // 2026-06-15, local time
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns today as YYYY-MM-DD', () => {
    expect(todayYmd()).toBe('2026-06-15')
  })

  it('treats an earlier date as past due', () => {
    expect(isPastDue('2026-06-14')).toBe(true)
  })

  it('treats today as not past due', () => {
    expect(isPastDue('2026-06-15')).toBe(false)
  })

  it('treats a future date as not past due', () => {
    expect(isPastDue('2026-06-16')).toBe(false)
  })
})
