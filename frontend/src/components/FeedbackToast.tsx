import { useEffect } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import type { ToastMessage } from '../feedback'

const VISIBLE_MS = 2200

interface FeedbackToastProps {
  toast: ToastMessage | null
  onDismiss: () => void
}

/**
 * App-root toast that slides down from the top. Deliberately dumb: it only shows
 * the latest message and hides itself; there's no queue or retry.
 */
export function FeedbackToast({ toast, onDismiss }: FeedbackToastProps) {
  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(onDismiss, VISIBLE_MS)
    return () => window.clearTimeout(timer)
  }, [toast, onDismiss])

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center">
      <AnimatePresence>
        {toast && (
          <motion.div
            key={toast.id}
            role="status"
            data-keep-panel-open
            initial={{ y: '-120%' }}
            animate={{ y: 0 }}
            exit={{ y: '-120%' }}
            transition={{ type: 'spring', stiffness: 500, damping: 40 }}
            className={`mt-3 rounded-lg px-5 py-2 text-sm font-semibold shadow-lg ${
              toast.tone === 'success' ? 'bg-emerald-700' : 'bg-red-700'
            }`}
          >
            {toast.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
