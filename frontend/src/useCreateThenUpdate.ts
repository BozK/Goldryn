import { useRef, useState } from 'react'

interface CreateThenUpdateOptions<T, P> {
  /** The saved resource, or null for a draft that hasn't been POSTed yet. */
  initial: T | null
  /** Fields a draft starts with (e.g. a maintenance record's default date). */
  initialPending?: P
  /** Whether the buffered draft fields are enough to POST (e.g. an item needs a name). */
  canCreate: (pending: P) => boolean
  /** Both callbacks resolve to undefined on failure; the failure is already toasted. */
  create: (fields: P) => Promise<T | undefined>
  update: (id: number, fields: P) => Promise<T | undefined>
  onCreated?: (created: T) => void
}

/**
 * Save-on-blur for one resource: the first save POSTs, every save after that PATCHes.
 *
 * While the resource is still a draft, saved fields are buffered and sent together
 * in the POST once `canCreate` allows it. A save that arrives while that POST is in
 * flight waits for it and then PATCHes, so two quick blurs never create two rows.
 */
export function useCreateThenUpdate<T extends { id: number }, P extends object>(
  options: CreateThenUpdateOptions<T, P>,
) {
  const [saved, setSaved] = useState<T | null>(options.initial)
  const savedRef = useRef<T | null>(options.initial)
  const pendingRef = useRef<P>(options.initialPending ?? ({} as P))
  const creatingRef = useRef<Promise<T | undefined> | null>(null)

  const replace = (next: T) => {
    savedRef.current = next
    setSaved(next)
  }

  const save = async (fields: P): Promise<T | undefined> => {
    if (savedRef.current === null) {
      const inFlight = creatingRef.current
      if (inFlight === null) {
        pendingRef.current = { ...pendingRef.current, ...fields }
        if (!options.canCreate(pendingRef.current)) return undefined

        const creating = options.create(pendingRef.current)
        creatingRef.current = creating
        const created = await creating
        creatingRef.current = null
        if (created) {
          pendingRef.current = {} as P
          replace(created)
          options.onCreated?.(created)
        }
        return created
      }

      const created = await inFlight
      if (!created) {
        // The POST failed; keep these fields for the next attempt.
        pendingRef.current = { ...pendingRef.current, ...fields }
        return undefined
      }
    }

    const current = savedRef.current
    if (current === null) return undefined
    const updated = await options.update(current.id, fields)
    if (updated) replace(updated)
    return updated
  }

  return { saved, save, replace }
}
