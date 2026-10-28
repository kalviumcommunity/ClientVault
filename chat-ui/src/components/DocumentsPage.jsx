/**
 * DocumentsPage — Document Library (mock-ux.html §4. Document Library).
 * Shows per-client corpus documents and indexing status.
 */
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'

const CORPUS = {
  'ACME-001': [
    { name: 'acme_onboarding_guide.md',    type: 'Onboarding', status: 'indexed',   chunks: 42 },
    { name: 'acme_contractor_access.md',   type: 'Onboarding', status: 'indexed',   chunks: 28 },
    { name: 'acme_service_level_agreement.txt', type: 'SLA',   status: 'indexed',   chunks: 19 },
    { name: 'acme_warehouse_api_runbook.md',    type: 'Runbook', status: 'indexed', chunks: 55 },
    { name: 'acme_incident_escalation.txt',     type: 'Runbook', status: 'indexed', chunks: 23 },
  ],
  'NEXUS-002': [
    { name: 'nexus_partner_onboarding.txt',   type: 'Onboarding', status: 'indexed', chunks: 31 },
    { name: 'nexus_compliance_guide.md',      type: 'Compliance', status: 'indexed', chunks: 48 },
    { name: 'nexus_service_level_agreement.txt', type: 'SLA',    status: 'indexed', chunks: 17 },
    { name: 'nexus_payment_gateway_runbook.html', type: 'Runbook', status: 'indexed', chunks: 63 },
    { name: 'nexus_database_failover_runbook.md', type: 'Runbook', status: 'indexed', chunks: 44 },
  ],
  'VERTEX-003': [
    { name: 'vertex_clinician_onboarding.html',     type: 'Onboarding', status: 'indexed', chunks: 39 },
    { name: 'vertex_hipaa_security_policy.md',      type: 'Policy',     status: 'indexed', chunks: 52 },
    { name: 'vertex_telehealth_sla.txt',            type: 'SLA',        status: 'indexed', chunks: 14 },
    { name: 'vertex_ehr_disaster_recovery.html',    type: 'Runbook',    status: 'indexed', chunks: 61 },
    { name: 'vertex_telehealth_outage_runbook.md',  type: 'Runbook',    status: 'indexed', chunks: 37 },
  ],
}

const CLIENT_NAMES = {
  'ACME-001':   'ACME Corp',
  'NEXUS-002':  'Nexus Financial Technologies',
  'VERTEX-003': 'Vertex Health Systems',
}

const STATUS_STYLE = {
  indexed:    { cls: 'border-success/40 bg-success/10 text-success',             label: 'Indexed',     Icon: CheckCircle2 },
  reindexing: { cls: 'border-warning/40 bg-warning/10 text-warning',             label: 'Re-indexing', Icon: Loader2 },
  failed:     { cls: 'border-destructive/40 bg-destructive/10 text-destructive', label: 'Failed',      Icon: XCircle },
}

export default function DocumentsPage({ activeClient, onSelectClient }) {
  const selectedClient = activeClient || 'ACME-001'
  const docs = CORPUS[selectedClient] || []
  const clientName = CLIENT_NAMES[selectedClient]

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6 content-fade">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold">Document Library</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {clientName} · {selectedClient} · {docs.length} documents
          </p>
        </div>
        {/* Client switcher */}
        <div className="flex gap-2 flex-wrap">
          {Object.keys(CORPUS).map(cid => (
            <button
              key={cid}
              onClick={() => onSelectClient(cid)}
              className={[
                'text-xs px-3 py-1.5 rounded-full border font-mono transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
                cid === selectedClient
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-transparent text-muted-foreground border-border hover:text-foreground hover:border-iri-violet/50',
              ].join(' ')}
            >
              {cid}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {docs.map((doc, i) => {
          const st = STATUS_STYLE[doc.status] || STATUS_STYLE.indexed
          return (
            <div
              key={i}
              className="bg-card border border-border rounded-xl px-4 py-3 flex items-center justify-between gap-3"
            >
              <div>
                <p className="font-mono text-sm font-medium break-all">{doc.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{doc.type} · {doc.chunks} chunks</p>
              </div>
              <span className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full border shrink-0 ${st.cls}`}>
                <st.Icon className="size-3.5" aria-hidden="true" />
                {st.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
