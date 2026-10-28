/**
 * ClientVault — App root
 *
 * Manages page routing and shared state (active page, active client).
 * Navigation is handled client-side without a router library (single-page).
 * Stack: React 18 + Vite + Tailwind CSS (PRD-prescribed).
 */
import { useState, useCallback } from 'react'
import TopNav        from './components/TopNav'
import DashboardPage from './components/DashboardPage'
import ClientsPage   from './components/ClientsPage'
import KnowledgePage from './components/KnowledgePage'
import DocumentsPage from './components/DocumentsPage'
import UploadPage    from './components/UploadPage'

export default function App() {
  const [activePage,   setActivePage]   = useState('dashboard')
  const [activeClient, setActiveClient] = useState(null) // e.g. 'NEXUS-002'

  // Knowledge Search history, one thread per client: { [clientId|'']: turns[] }
  const [conversations, setConversations] = useState({})
  const updateTurns = useCallback((clientId, updater) => {
    const key = clientId || ''
    setConversations(prev => ({ ...prev, [key]: updater(prev[key] || []) }))
  }, [])

  const navigate = (page) => setActivePage(page)

  const selectClient = (clientId) => {
    setActiveClient(clientId)
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <TopNav
        activePage={activePage}
        onNavigate={navigate}
        activeClient={activeClient}
      />

      {/* Skip-to-content link for keyboard / AT users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-14 focus:left-4 focus:z-50 focus:bg-white focus:px-4 focus:py-2 focus:rounded focus:shadow-lg focus:text-fuchsia-600 focus:font-semibold"
      >
        Skip to main content
      </a>

      <div id="main-content" className="flex-1">
        {activePage === 'dashboard' && (
          <DashboardPage
            onNavigate={navigate}
            onSelectClient={selectClient}
          />
        )}
        {activePage === 'clients' && (
          <ClientsPage
            activeClient={activeClient}
            onSelectClient={selectClient}
            onNavigate={navigate}
          />
        )}
        {activePage === 'knowledge' && (
          <KnowledgePage
            activeClient={activeClient}
            onNavigate={navigate}
            turns={conversations[activeClient || ''] || []}
            onTurnsChange={updateTurns}
          />
        )}
        {activePage === 'documents' && (
          <DocumentsPage
            activeClient={activeClient}
            onSelectClient={selectClient}
          />
        )}
        {activePage === 'upload' && (
          <UploadPage activeClient={activeClient} />
        )}
      </div>
    </div>
  )
}
