/**
 * DashboardPage — Entry-point screen (mock-ux.html §1. Dashboard).
 * Shows v1.2 KPI targets and a shortcut to select a client / open knowledge.
 */

const KPI_TARGETS = [
  { label: 'Top-5 Recall',          value: '≥ 85%',  sub: 'target · Day 15',              highlight: true },
  { label: 'Account Isolation',     value: '≥ 95%',  sub: 'no wrong-client evidence',     highlight: true },
  { label: 'Search→Source ≤ 60s',   value: '≤ 60 s', sub: 'median · 30 queries · Day 18', highlight: true },
  { label: 'Unsupported-Query Safety', value: '100%', sub: 'out-of-corpus → refusal',      highlight: true },
]

const CORPUS_STATS = [
  { label: 'Documents indexed', value: '15 / 15', sub: '100% metadata' },
  { label: 'Active clients',    value: '3',        sub: 'ACME · NEXUS · VERTEX' },
  { label: 'Indexing in progress', value: '0',     sub: 'all chunks validated' },
]

const CLIENTS = [
  { id: 'ACME-001',   name: 'ACME Corp',                docs: 5, status: '100% indexed' },
  { id: 'NEXUS-002',  name: 'Nexus Financial Technologies', docs: 5, status: '100% indexed' },
  { id: 'VERTEX-003', name: 'Vertex Health Systems',    docs: 5, status: '100% indexed' },
]

export default function DashboardPage({ onNavigate, onSelectClient }) {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8 content-fade">
      {/* Hero */}
      <div
        className="rounded-2xl p-8 text-white"
        style={{ background: 'linear-gradient(135deg, #0f172a, #1e293b)' }}
      >
        <p className="text-xs font-bold uppercase tracking-widest text-fuchsia-400 mb-3">
          ClientVault · Client Support Knowledge Assistant
        </p>
        <h1 className="text-2xl font-bold mb-2">Dashboard</h1>
        <p className="text-slate-300 text-sm max-w-xl">
          90-second health check. Select the affected client to restrict retrieval,
          then open Knowledge Search for grounded, evidence-backed answers.
        </p>
      </div>

      {/* KPI targets */}
      <section aria-labelledby="kpi-heading">
        <h2 id="kpi-heading" className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3">
          v1.2 KPI Targets
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {KPI_TARGETS.map(k => (
            <div
              key={k.label}
              className="rounded-xl p-4 border"
              style={{ background: '#fdf2f8', borderColor: '#d946ef' }}
            >
              <div className="text-xs font-semibold text-fuchsia-800 uppercase tracking-wide mb-1">{k.label}</div>
              <div className="text-xl font-bold text-slate-800">{k.value}</div>
              <div className="text-xs text-fuchsia-700 mt-0.5">{k.sub}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Corpus health */}
      <div className="grid grid-cols-3 gap-3">
        {CORPUS_STATS.map(s => (
          <div key={s.label} className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">{s.label}</div>
            <div className="text-xl font-bold text-slate-800">{s.value}</div>
            <div className="text-xs text-emerald-600 mt-0.5">{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Quick-select client */}
      <section aria-labelledby="client-select-heading">
        <h2 id="client-select-heading" className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-3">
          Select Affected Client → Open Knowledge Search
        </h2>
        <div className="space-y-2">
          {CLIENTS.map(c => (
            <div
              key={c.id}
              className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center justify-between shadow-sm"
            >
              <div>
                <span className="font-semibold text-slate-800 text-sm">{c.name}</span>
                <span className="ml-2 text-xs text-slate-500">{c.id} · {c.docs} docs · {c.status}</span>
              </div>
              <button
                onClick={() => { onSelectClient(c.id); onNavigate('knowledge'); }}
                className="text-xs font-bold bg-fuchsia-500 hover:bg-fuchsia-600 text-white px-3 py-1.5 rounded-full transition-colors focus-visible:outline-2 focus-visible:outline-fuchsia-400"
              >
                Open knowledge →
              </button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
