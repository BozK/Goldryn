import { Children } from 'react'
import type { ReactNode } from 'react'

/** Vertical gap between cards, in px. Rows are 1px tall, so it's added to each span. */
const GAP = 12

/**
 * Two-column masonry. Each cell spans as many 1px grid rows as it is tall, so
 * auto-placement drops the next card under whichever column ends first, instead of
 * starting a new row below the taller of two neighbors.
 *
 * Cards keep their DOM order and React identity; only their grid placement changes,
 * so a card that grows while being edited never remounts.
 */
export function MasonryGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid auto-rows-[1px] grid-cols-2 gap-x-3">
      {Children.map(
        children,
        (child) =>
          child && (
            <div ref={spanOwnHeight} className="self-start">
              {child}
            </div>
          ),
      )}
    </div>
  )
}

// Writes the style directly rather than through state: ResizeObserver callbacks run
// before paint, so the first frame is already laid out, with no overlapping cards.
function spanOwnHeight(cell: HTMLDivElement | null) {
  if (!cell) return
  const observer = new ResizeObserver(([entry]) => {
    cell.style.gridRowEnd = `span ${Math.ceil(entry.borderBoxSize[0].blockSize) + GAP}`
  })
  observer.observe(cell)
  return () => observer.disconnect()
}
