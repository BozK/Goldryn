import { motion } from 'motion/react'
import type { ItemSummary } from '../lib/GoldrynModels'
import { formatDay, isPastDue } from '../lib/dates'
import { resolveColor } from '../palette'

interface ItemCardProps {
  item: ItemSummary
  isSelected: boolean
  isDimmed: boolean
  onSelect: (id: number) => void
}

export function ItemCard({ item, isSelected, isDimmed, onSelect }: ItemCardProps) {
  const { bg, accent } = resolveColor(item.color)
  const overdue = item.next_due !== null && isPastDue(item.next_due)

  return (
    <motion.button
      layout
      type="button"
      data-keep-panel-open
      onClick={() => onSelect(item.id)}
      style={{ backgroundColor: bg, borderColor: accent }}
      animate={{ opacity: isDimmed ? 0.55 : 1 }}
      whileHover={{ scale: 1.03 }}
      className={`clip-corners flex h-36 w-60 shrink-0 flex-col justify-between border-l-8 px-8 py-6 text-left ${
        isSelected ? 'brightness-125' : ''
      }`}
    >
      <span className="line-clamp-2 text-lg font-semibold">{item.name}</span>
      {item.next_due && (
        <span className={`text-sm ${overdue ? 'font-semibold text-red-300' : 'text-white/75'}`}>
          {overdue ? 'Overdue · ' : 'Due '}
          {formatDay(item.next_due)}
        </span>
      )}
    </motion.button>
  )
}
