import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import type { ItemSummary } from '../lib/GoldrynModels'
import { api, ApiError } from '../api/client'
import { isAuthFailure } from '../lib/feedback'
import { ItemCard } from './ItemCard'

interface LandingPageProps {
  /** Bumped by App after every successful mutation so the grid stays current. */
  refreshKey: number
  isPanelOpen: boolean
  selectedItemId: number | null
  onSelectItem: (id: number) => void
  onNewItem: () => void
  onLogout: () => void
  onUnauthorized: () => void
}

export function LandingPage({
  refreshKey,
  isPanelOpen,
  selectedItemId,
  onSelectItem,
  onNewItem,
  onLogout,
  onUnauthorized,
}: LandingPageProps) {
  const [items, setItems] = useState<ItemSummary[]>([])
  const [loadFailed, setLoadFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .listItems()
      .then((rows) => {
        if (cancelled) return
        setItems(rows)
        setLoadFailed(false)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && isAuthFailure(err.status)) onUnauthorized()
        else setLoadFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey, attempt, onUnauthorized])

  return (
    <div className="px-8 py-6">
      <header className="mb-8 flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight text-gold">Goldryn</h1>
        <button type="button" onClick={onLogout} className="text-sm text-white/60 hover:text-white">
          Log out
        </button>
      </header>

      {loadFailed && (
        <p className="mb-4 text-sm text-red-300">
          Couldn't load items.{' '}
          <button type="button" className="underline" onClick={() => setAttempt((n) => n + 1)}>
            Retry
          </button>
        </p>
      )}

      <div className="flex items-start gap-4">
        <motion.button
          layout
          type="button"
          data-keep-panel-open
          onClick={onNewItem}
          aria-label="New item"
          title="New item"
          className="clip-corners flex h-36 w-14 shrink-0 items-center justify-center bg-surface-raised text-3xl text-gold transition-colors hover:bg-surface-line"
        >
          +
        </motion.button>

        <div className="flex flex-wrap gap-4">
          {items.map((item) => (
            <ItemCard
              key={item.id}
              item={item}
              isSelected={item.id === selectedItemId}
              isDimmed={isPanelOpen && item.id !== selectedItemId}
              onSelect={onSelectItem}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
