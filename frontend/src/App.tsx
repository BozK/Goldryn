import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence } from 'motion/react'
import { api, ApiError } from './api/client'
import { isAuthFailure, SAVED_TEXT, saveErrorText } from './lib/feedback'
import type { Mutate, ToastMessage, ToastTone } from './lib/feedback'
import type { TagSummary } from './lib/GoldrynModels'
import { FeedbackToast } from './components/FeedbackToast'
import { ItemPanel } from './components/ItemPanel'
import type { PanelEntry } from './components/ItemPanel'
import { LandingPage } from './components/LandingPage'
import { LoginScreen } from './components/LoginScreen'

type AuthState = 'checking' | 'anonymous' | 'authenticated'
type ViewMode = 'list' | 'panel'

function App() {
  const [auth, setAuth] = useState<AuthState>('checking')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null)
  // Identifies one "opening" of the panel. Kept separate from selectedItemId so a
  // new item getting its id on first save doesn't remount (and re-animate) the panel.
  const [panelKey, setPanelKey] = useState(0)
  const [panelEntry, setPanelEntry] = useState<PanelEntry>('right')
  const [refreshKey, setRefreshKey] = useState(0)
  const [toast, setToast] = useState<ToastMessage | null>(null)
  const toastCounter = useRef(0)
  const [tagSuggestions, setTagSuggestions] = useState<TagSummary[]>([])

  useEffect(() => {
    api
      .me()
      .then(() => setAuth('authenticated'))
      .catch(() => setAuth('anonymous'))
  }, [])

  // Refetched with the grid (every successful write bumps refreshKey), so a tag created
  // on one item is suggested on the next. A failed fetch keeps the old list: suggestions
  // are a convenience, and the grid's own fetch handles an expired session.
  useEffect(() => {
    if (auth !== 'authenticated') return
    let cancelled = false
    api
      .listTags()
      .then((tags) => !cancelled && setTagSuggestions(tags))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [auth, refreshKey])

  const showToast = useCallback((tone: ToastTone, text: string) => {
    toastCounter.current += 1
    setToast({ id: toastCounter.current, tone, text })
  }, [])

  const dismissToast = useCallback(() => setToast(null), [])

  const closePanel = useCallback(() => {
    setViewMode('list')
    setSelectedItemId(null)
  }, [])

  const openPanel = useCallback(
    (itemId: number | null) => {
      // Re-clicking the card that's already open shouldn't slide the panel out and back in.
      if (viewMode === 'panel' && itemId !== null && itemId === selectedItemId) return
      setSelectedItemId(itemId)
      setPanelEntry(itemId === null ? 'left' : 'right')
      setPanelKey((key) => key + 1)
      setViewMode('panel')
    },
    [viewMode, selectedItemId],
  )

  const handleUnauthorized = useCallback(() => {
    closePanel()
    setAuth('anonymous')
  }, [closePanel])

  // Every POST/PATCH/DELETE goes through here: toast the outcome, refresh the grid
  // on success, and drop back to the login screen if the session has expired.
  const mutate: Mutate = useCallback(
    async <T,>(call: () => Promise<T>): Promise<T | undefined> => {
      try {
        const result = await call()
        showToast('success', SAVED_TEXT)
        setRefreshKey((key) => key + 1)
        return result
      } catch (err) {
        const status = err instanceof ApiError ? err.status : 0
        showToast('error', saveErrorText(status))
        if (isAuthFailure(status)) handleUnauthorized()
        return undefined
      }
    },
    [showToast, handleUnauthorized],
  )

  const handleItemCreated = useCallback((id: number) => setSelectedItemId(id), [])

  const handleLogout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // The session is gone either way from the user's point of view.
    }
    closePanel()
    setAuth('anonymous')
  }, [closePanel])

  const handleLoggedIn = useCallback(() => {
    setRefreshKey((key) => key + 1)
    setAuth('authenticated')
  }, [])

  const handleLoginError = useCallback((text: string) => showToast('error', text), [showToast])

  // The grid makes room on the side the panel isn't on: a new item's panel fills the
  // left half, an existing item's panel the right three fifths.
  const gridLayout = viewMode === 'list' ? 'w-full' : panelEntry === 'left' ? 'ml-auto w-1/2' : 'w-2/5'

  return (
    <>
      <FeedbackToast toast={toast} onDismiss={dismissToast} />

      {auth === 'checking' && (
        <main className="flex min-h-screen items-center justify-center text-white/50">Loading...</main>
      )}

      {auth === 'anonymous' && <LoginScreen onLoggedIn={handleLoggedIn} onError={handleLoginError} />}

      {auth === 'authenticated' && (
        <div className="relative flex h-screen overflow-hidden">
          <section className={`h-full overflow-y-auto ${gridLayout}`}>
            <LandingPage
              refreshKey={refreshKey}
              isPanelOpen={viewMode === 'panel'}
              selectedItemId={selectedItemId}
              onSelectItem={openPanel}
              onNewItem={() => openPanel(null)}
              onLogout={handleLogout}
              onUnauthorized={handleUnauthorized}
            />
          </section>

          <AnimatePresence mode="wait">
            {viewMode === 'panel' && (
              <ItemPanel
                key={panelKey}
                itemId={selectedItemId}
                enterFrom={panelEntry}
                tagSuggestions={tagSuggestions}
                mutate={mutate}
                onCreated={handleItemCreated}
                onClose={closePanel}
                onUnauthorized={handleUnauthorized}
              />
            )}
          </AnimatePresence>
        </div>
      )}
    </>
  )
}

export default App
