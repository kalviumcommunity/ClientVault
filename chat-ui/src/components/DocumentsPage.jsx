/**
 * DocumentsPage — Document Library (mock-ux.html §4. Document Library).
 * Shows per-client corpus documents and indexing status.
 */

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
  indexed:    { bg: '#e9f6ef', border: '#3fa36b', text: '#1f6b43', label: '✓ Indexed' },
  reindexing: { bg: '#fdf4e6', border: '#e8a03c', text: '#8a5a12', label: '⏳ Re-indexing' },
  failed:     { bg: '#fdeef0', border: '#d9534f', text: '#9c2f2b', label: '✕ Failed' },
}

export default function DocumentsPage({ activeClient, onSelectClient }) {
  const selectedClient = activeClient || 'ACME-001'
  const docs = CORPUS[selectedClient] || []
  const clientName = CLIENT_NAMES[selectedClient]

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-6 content-fade">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Document Library</h1>
          <p className="text-sm text-slate-500 mt-1">
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
                'text-xs px-3 py-1.5 rounded-full border font-semibold transition-colors',
                cid === selectedClient
                  ? 'bg-fuchsia-500 text-white border-fuchsia-500'
                  : 'bg-white text-slate-600 border-slate-300 hover:border-fuchsia-400',
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
              className="bg-white border border-slate-200 rounded-xl px-4 py-3 flex items-center justify-between shadow-sm"
            >
              <div>
                <p className="font-mono text-sm font-medium text-slate-800">{doc.name}</p>
                <p className="text-xs text-slate-500 mt-0.5">{doc.type} · {doc.chunks} chunks</p>
              </div>
              <span
                className="text-xs font-semibold px-2.5 py-1 rounded-full border shrink-0"
                style={{ background: st.bg, borderColor: st.border, color: st.text }}
              >
                {st.label} {doc.chunks ? `· ${doc.chunks} chunks` : ''}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
