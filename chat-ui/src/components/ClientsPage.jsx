/**
 * ClientsPage — Account browser (mock-ux.html §2. Clients).
 * Filter / select an account to restrict retrieval scope.
 */

const CLIENTS = [
  { id: 'ACME-001',   name: 'ACME Corp',                        docs: 5, status: 'indexed',   statusLabel: '100% indexed' },
  { id: 'NEXUS-002',  name: 'Nexus Financial Technologies',     docs: 5, status: 'indexed',   statusLabel: '100% indexed' },
  { id: 'VERTEX-003', name: 'Vertex Health Systems',            docs: 5, status: 'indexed',   statusLabel: '100% indexed' },
]

const STATUS_COLORS = {
  indexed:    { bg: '#e9f6ef', border: '#3fa36b', text: '#1f6b43' },
  reindexing: { bg: '#fdf4e6', border: '#e8a03c', text: '#8a5a12' },
  failed:     { bg: '#fdeef0', border: '#d9534f', text: '#9c2f2b' },
}

export default function ClientsPage({ activeClient, onSelectClient, onNavigate }) {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6 content-fade">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Clients</h1>
        <p className="text-sm text-slate-500 mt-1">
          Select an account to restrict retrieval scope (FR-01, FR-02).
        </p>
      </div>

      {/* Note: account isolation filter is the primary purpose */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-sm text-blue-800">
        <strong>Account isolation active.</strong> Selecting a client locks retrieval to that account's documents only.
        Target: ≥ 95% isolation (PRD v1.2 KPI).
      </div>

      {/* Client list */}
      <div className="space-y-2">
        {CLIENTS.map(c => {
          const colors = STATUS_COLORS[c.status] || STATUS_COLORS.indexed
          const isActive = activeClient === c.id
          return (
            <div
              key={c.id}
              className={[
                'bg-white border rounded-xl px-4 py-3 flex items-center justify-between shadow-sm transition-all',
                isActive ? 'border-fuchsia-400 ring-2 ring-fuchsia-200' : 'border-slate-200',
              ].join(' ')}
            >
              <div>
                <span className="font-semibold text-slate-800">{c.name}</span>
                <span className="ml-2 text-xs text-slate-400 font-mono">{c.id}</span>
                <div className="text-xs text-slate-500 mt-0.5">{c.docs} documents</div>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className="text-xs font-semibold px-2 py-0.5 rounded-full border"
                  style={{ background: colors.bg, borderColor: colors.border, color: colors.text }}
                >
                  {c.statusLabel}
                </span>
                <button
                  onClick={() => { onSelectClient(c.id); onNavigate('knowledge'); }}
                  className="text-xs font-bold bg-fuchsia-500 hover:bg-fuchsia-600 text-white px-3 py-1.5 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-fuchsia-400"
                >
                  Open knowledge →
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
