/**
 * TopNav — ClientVault persistent top navigation bar.
 * Navigation pattern and active-link style from mock-ux.html §topnav.
 */
import { LayoutDashboard, Users, Search, Library, Upload, Lock } from 'lucide-react'

const NAV_ITEMS = [
  { id: 'dashboard',  label: 'Dashboard',        Icon: LayoutDashboard },
  { id: 'clients',    label: 'Clients',          Icon: Users },
  { id: 'knowledge',  label: 'Knowledge Search', Icon: Search },
  { id: 'documents',  label: 'Documents',        Icon: Library },
  { id: 'upload',     label: 'Upload',           Icon: Upload },
]

export default function TopNav({ activePage, onNavigate, activeClient }) {
  return (
    <header
      className="sticky top-0 z-30 flex items-center gap-1.5 flex-wrap border-b border-border bg-background/80 backdrop-blur-md px-4 py-2.5"
      role="navigation"
      aria-label="ClientVault main navigation"
    >
      {/* Brand */}
      <span className="font-semibold tracking-[0.18em] text-sm mr-3 shrink-0">
        <span className="bg-linear-to-r from-violet-400 via-pink-400 to-sky-400 bg-clip-text text-transparent">CLIENT</span>VAULT
      </span>

      {/* Nav links */}
      {NAV_ITEMS.map(({ id, label, Icon }) => (
        <button
          key={id}
          onClick={() => onNavigate(id)}
          className={[
            'inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
            activePage === id
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-secondary',
          ].join(' ')}
          aria-current={activePage === id ? 'page' : undefined}
        >
          <Icon className="size-3.5" aria-hidden="true" />
          {label}
        </button>
      ))}

      <span className="flex-1" />

      {/* Active client badge */}
      {activeClient
        ? (
          <span className="inline-flex items-center gap-1.5 text-xs border border-iri-violet/40 bg-iri-violet/10 rounded-full px-2.5 py-1 text-violet-300 font-mono shrink-0">
            <Lock className="size-3" aria-hidden="true" />
            {activeClient}
          </span>
        )
        : (
          <span className="text-xs border border-border rounded-full px-2.5 py-1 text-muted-foreground shrink-0">
            No client selected
          </span>
        )
      }
    </header>
  )
}
