/**
 * DashboardPage — Entry-point screen (mock-ux.html §1. Dashboard).
 * Shows v1.2 KPI targets and a shortcut to select a client / open knowledge.
 */
import { ArrowRight } from 'lucide-react'
import { Button } from '@/components/ui/button'

const KPI_TARGETS = [
  { label: 'Top-5 Recall',          value: '≥ 85%',  sub: 'target · Day 15' },
  { label: 'Account Isolation',     value: '≥ 95%',  sub: 'no wrong-client evidence' },
  { label: 'Search→Source ≤ 60s',   value: '≤ 60 s', sub: 'median · 30 queries · Day 18' },
  { label: 'Unsupported-Query Safety', value: '100%', sub: 'out-of-corpus → refusal' },
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

const SECTION_HEADING = 'text-xs font-medium text-muted-foreground uppercase tracking-[0.12em] mb-3'

export default function DashboardPage({ onNavigate, onSelectClient }) {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-8 content-fade">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-2xl border border-border bg-card p-8">
        <div
          className="pointer-events-none absolute -bottom-16 left-10 right-10 h-24 rounded-full opacity-30 blur-3xl"
          style={{ background: 'linear-gradient(90deg, #8b5cf6, #ec4899, #60a5fa)' }}
          aria-hidden="true"
        />
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground mb-3">
          ClientVault · Client Support Knowledge Assistant
        </p>
        <h1 className="text-2xl font-semibold mb-2">Dashboard</h1>
        <p className="text-muted-foreground text-sm max-w-xl">
          90-second health check. Select the affected client to restrict retrieval,
          then open Knowledge Search for grounded, evidence-backed answers.
        </p>
      </div>

      {/* KPI targets */}
      <section aria-labelledby="kpi-heading">
        <h2 id="kpi-heading" className={SECTION_HEADING}>v1.2 KPI Targets</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {KPI_TARGETS.map(k => (
            <div key={k.label} className="rounded-xl p-4 border border-iri-violet/30 bg-iri-violet/5">
              <div className="text-xs font-medium text-violet-300 uppercase tracking-wide mb-1">{k.label}</div>
              <div className="text-xl font-semibold">{k.value}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{k.sub}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Corpus health */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {CORPUS_STATS.map(s => (
          <div key={s.label} className="bg-card rounded-xl border border-border p-4">
            <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">{s.label}</div>
            <div className="text-xl font-semibold">{s.value}</div>
            <div className="text-xs text-success mt-0.5">{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Quick-select client */}
      <section aria-labelledby="client-select-heading">
        <h2 id="client-select-heading" className={SECTION_HEADING}>
          Select Affected Client → Open Knowledge Search
        </h2>
        <div className="space-y-2">
          {CLIENTS.map(c => (
            <div
              key={c.id}
              className="bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-between gap-3"
            >
              <div className="min-w-0">
                <span className="font-medium text-sm">{c.name}</span>
                <span className="ml-2 text-xs text-muted-foreground">{c.id} · {c.docs} docs · {c.status}</span>
              </div>
              <Button size="sm" className="rounded-full" onClick={() => { onSelectClient(c.id); onNavigate('knowledge'); }}>
                Open knowledge <ArrowRight data-icon="inline-end" />
              </Button>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}
