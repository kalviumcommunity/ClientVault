/**
 * ClientsPage — Account browser (mock-ux.html §2. Clients).
 * Filter / select an account to restrict retrieval scope.
 */
import { ArrowRight, ShieldCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'

const CLIENTS = [
  { id: 'ACME-001',   name: 'ACME Corp',                        docs: 5, status: 'indexed',   statusLabel: '100% indexed' },
  { id: 'NEXUS-002',  name: 'Nexus Financial Technologies',     docs: 5, status: 'indexed',   statusLabel: '100% indexed' },
  { id: 'VERTEX-003', name: 'Vertex Health Systems',            docs: 5, status: 'indexed',   statusLabel: '100% indexed' },
]

const STATUS_CLASSES = {
  indexed:    'border-success/40 bg-success/10 text-success',
  reindexing: 'border-warning/40 bg-warning/10 text-warning',
  failed:     'border-destructive/40 bg-destructive/10 text-destructive',
}

export default function ClientsPage({ activeClient, onSelectClient, onNavigate }) {
  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6 content-fade">
      <div>
        <h1 className="text-xl font-semibold">Clients</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Select an account to restrict retrieval scope (FR-01, FR-02).
        </p>
      </div>

      {/* Note: account isolation filter is the primary purpose */}
      <div className="flex gap-2.5 bg-sky-400/10 border border-sky-400/30 rounded-lg px-4 py-3 text-sm text-sky-200">
        <ShieldCheck className="size-4 shrink-0 mt-0.5" aria-hidden="true" />
        <p><strong className="font-medium">Account isolation active.</strong> Selecting a client locks retrieval to that account's documents only.
        Target: ≥ 95% isolation (PRD v1.2 KPI).</p>
      </div>

      {/* Client list */}
      <div className="space-y-2">
        {CLIENTS.map(c => {
          const statusClass = STATUS_CLASSES[c.status] || STATUS_CLASSES.indexed
          const isActive = activeClient === c.id
          return (
            <div
              key={c.id}
              className={[
                'bg-card border rounded-xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap transition-all',
                isActive ? 'border-iri-violet/60 ring-2 ring-iri-violet/20' : 'border-border',
              ].join(' ')}
            >
              <div>
                <span className="font-medium">{c.name}</span>
                <span className="ml-2 text-xs text-muted-foreground font-mono">{c.id}</span>
                <div className="text-xs text-muted-foreground mt-0.5">{c.docs} documents</div>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${statusClass}`}>
                  {c.statusLabel}
                </span>
                <Button size="sm" className="rounded-full" onClick={() => { onSelectClient(c.id); onNavigate('knowledge'); }}>
                  Open knowledge <ArrowRight data-icon="inline-end" />
                </Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
