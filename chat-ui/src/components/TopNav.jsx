/**
 * TopNav — ClientVault persistent top navigation bar.
 * Navigation pattern and active-link style from mock-ux.html §topnav.
 */

const NAV_ITEMS = [
  { id: 'dashboard',  label: '📊 Dashboard'       },
  { id: 'clients',    label: '👥 Clients'          },
  { id: 'knowledge',  label: '🔍 Knowledge Search' },
  { id: 'documents',  label: '📚 Documents'        },
  { id: 'upload',     label: '⬆ Upload'            },
]

export default function TopNav({ activePage, onNavigate, activeClient }) {
  return (
    <header
      className="flex items-center gap-2 flex-wrap bg-slate-900 text-white px-4 py-2.5"
      role="navigation"
      aria-label="ClientVault main navigation"
    >
      {/* Brand */}
      <span className="font-extrabold tracking-wide text-sm mr-2 shrink-0">
        <span className="text-fuchsia-400">CLIENT</span>VAULT
      </span>

      {/* Nav links */}
      {NAV_ITEMS.map(item => (
        <button
          key={item.id}
          onClick={() => onNavigate(item.id)}
          className={[
            'text-xs font-semibold px-3 py-1.5 rounded-md transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-fuchsia-400',
            activePage === item.id
              ? 'bg-fuchsia-500 text-white'
              : 'border border-white/30 text-white/70 hover:bg-white/10',
          ].join(' ')}
          aria-current={activePage === item.id ? 'page' : undefined}
        >
          {item.label}
        </button>
      ))}

      <span className="flex-1" />

      {/* Active client badge */}
      {activeClient
        ? (
          <span className="text-xs border border-fuchsia-400/60 rounded px-2 py-1 text-fuchsia-300 font-mono shrink-0">
            {activeClient}
          </span>
        )
        : (
          <span className="text-xs border border-white/20 rounded px-2 py-1 text-white/40 shrink-0">
            No client selected
          </span>
        )
      }
    </header>
  )
}
