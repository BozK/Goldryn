import { useEffect, useRef } from 'react'
import { motion } from 'motion/react'

export type PanelEntry = 'left' | 'right'

interface ItemPanelProps {
  itemId: number | null
  /** New items slide in from the left, existing ones from the right. */
  enterFrom: PanelEntry
  onClose: () => void
}

export function ItemPanel({ itemId, enterFrom, onClose }: ItemPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const offscreen = enterFrom === 'left' ? '-100%' : '100%'

  useEffect(() => {
    // Escape doesn't move focus by itself, so blur first to flush any in-progress edit.
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
      onClose()
    }

    // A plain `click` (never a preventDefault'd mousedown), so the field's blur-save
    // has already fired by the time we close. Cards and the + control opt out via
    // data-keep-panel-open: they switch the panel instead of closing it.
    const handleClick = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element) || !target.isConnected) return
      if (panelRef.current?.contains(target)) return
      if (target.closest('[data-keep-panel-open]')) return
      onClose()
    }

    document.addEventListener('keydown', handleKeyDown)
    document.addEventListener('click', handleClick)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('click', handleClick)
    }
  }, [onClose])

  return (
    <motion.aside
      ref={panelRef}
      initial={{ x: offscreen }}
      animate={{ x: 0 }}
      exit={{ x: offscreen }}
      transition={{ type: 'spring', stiffness: 320, damping: 36 }}
      className="absolute inset-y-0 right-0 z-10 w-3/5 overflow-y-auto border-l border-surface-line bg-surface-raised shadow-2xl"
    >
      <button
        type="button"
        onClick={onClose}
        aria-label="Close"
        className="absolute top-4 right-4 z-10 rounded-full px-3 py-1 text-2xl leading-none text-white/70 hover:bg-white/10 hover:text-white"
      >
        ×
      </button>
      <div className="p-8">
        <p className="text-white/60">
          {itemId === null ? 'New item' : `Item #${itemId}`}: panel contents coming in the ItemPanel PR.
        </p>
      </div>
    </motion.aside>
  )
}
