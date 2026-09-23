import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence } from 'motion/react'
import { api } from './api/client'
import type { ToastMessage, ToastTone } from './feedback'
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

  useEffect(() => {
    api
      .me()
      .then(() => setAuth('authenticated'))
      .catch(() => setAuth('anonymous'))
  }, [])

  const showToast = useCallback((tone: ToastTone, text: string) => {
    toastCounter.current += 1
    setToast({ id: toastCounter.current, tone, text })
  }, [])

  const dismissToast = useCallback(() => setToast(null), [])

  const closePanel = useCallback(() => {
    setViewMode('list')
    setSelectedItemId(null)
  }, [])

  const openPanel = useCallback((itemId: number | null) => {
    setSelectedItemId(itemId)
    setPanelEntry(itemId === null ? 'left' : 'right')
    setPanelKey((key) => key + 1)
    setViewMode('panel')
  }, [])

  const handleUnauthorized = useCallback(() => {
    closePanel()
    setAuth('anonymous')
  }, [closePanel])

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

  return (
    <>
      <FeedbackToast toast={toast} onDismiss={dismissToast} />

      {auth === 'checking' && (
        <main className="flex min-h-screen items-center justify-center text-white/50">Loading...</main>
      )}

      {auth === 'anonymous' && <LoginScreen onLoggedIn={handleLoggedIn} onError={handleLoginError} />}

      {auth === 'authenticated' && (
        <div className="relative flex h-screen overflow-hidden">
          <section className={`h-full overflow-y-auto ${viewMode === 'panel' ? 'w-2/5' : 'w-full'}`}>
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
                onClose={closePanel}
              />
            )}
          </AnimatePresence>
        </div>
      )}
    </>
  )
}

export default App
