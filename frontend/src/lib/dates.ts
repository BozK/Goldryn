// "YYYY-MM-DD" values are calendar days, not instants. They're parsed as local
// dates so they never shift a day across time zones the way `new Date(ymd)` does.

function parseDay(ymd: string): Date {
  const [year, month, day] = ymd.split('-').map(Number)
  return new Date(year, month - 1, day)
}

const DAY_FORMAT: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric', year: 'numeric' }

/** "2026-11-15" -> "Nov 15, 2026" */
export function formatDay(ymd: string): string {
  return parseDay(ymd).toLocaleDateString(undefined, DAY_FORMAT)
}

/** ISO-8601 UTC timestamp -> local calendar day, e.g. "Jan 4, 2026" */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, DAY_FORMAT)
}

/** Today as "YYYY-MM-DD" in local time. */
export function todayYmd(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export function isPastDue(ymd: string): boolean {
  return ymd < todayYmd()
}
