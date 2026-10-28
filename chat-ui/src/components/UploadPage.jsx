/**
 * UploadPage — Document Upload & Indexing (mock-ux.html §5).
 * Admin screen — accepts file + client + doc type metadata.
 * No actual upload backend is connected; shows the PRD-specified UI states.
 */
import { useState } from 'react'
import { UploadCloud } from 'lucide-react'
import { Button } from '@/components/ui/button'

const CLIENTS   = ['ACME-001', 'NEXUS-002', 'VERTEX-003']
const DOC_TYPES = ['Onboarding', 'SLA', 'Runbook', 'Policy', 'Compliance']

export default function UploadPage({ activeClient }) {
  const [client,  setClient]  = useState(activeClient || CLIENTS[0])
  const [docType, setDocType] = useState(DOC_TYPES[0])
  const [file,    setFile]    = useState(null)
  const [notice,  setNotice]  = useState(null)  // { type: 'success'|'error', msg }

  const handleSubmit = e => {
    e.preventDefault()
    if (!file) { setNotice({ type: 'error', msg: 'Please select a file to upload.' }); return }
    // Simulate: in production, POST multipart to /ingest
    setNotice({
      type: 'success',
      msg: `${file.name} — queued for extraction → cleaning → chunking → embedding → indexing for ${client}.`,
    })
  }

  return (
    <div className="max-w-xl mx-auto px-4 py-8 content-fade">
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Document Upload &amp; Indexing</h1>
        <p className="text-sm text-muted-foreground mt-1">Admin workflow — add or re-index corpus documents (FR-12, FR-13).</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 bg-card border border-border rounded-2xl p-6">
        {/* Client selector */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1" htmlFor="upload-client">
            Client account <span className="text-destructive">*</span>
          </label>
          <select
            id="upload-client"
            value={client}
            onChange={e => setClient(e.target.value)}
            className="w-full border border-input bg-input/30 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          >
            {CLIENTS.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        {/* Doc type */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1" htmlFor="upload-doctype">
            Document type
          </label>
          <select
            id="upload-doctype"
            value={docType}
            onChange={e => setDocType(e.target.value)}
            className="w-full border border-input bg-input/30 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          >
            {DOC_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
        </div>

        {/* File dropzone */}
        <div>
          <label className="block text-xs font-medium text-muted-foreground mb-1" htmlFor="upload-file">
            File <span className="text-destructive">*</span> <span className="text-muted-foreground font-normal">(PDF · DOCX · TXT · MD · HTML)</span>
          </label>
          <div className="relative border-2 border-dashed border-input rounded-xl p-6 text-center hover:border-iri-violet/60 focus-within:ring-2 focus-within:ring-ring transition-colors">
            <input
              id="upload-file"
              type="file"
              accept=".pdf,.docx,.txt,.md,.html"
              className="absolute inset-0 opacity-0 cursor-pointer"
              onChange={e => { setFile(e.target.files?.[0] || null); setNotice(null) }}
            />
            {file
              ? <p className="text-sm font-medium text-violet-300 break-all">{file.name}</p>
              : <p className="flex items-center justify-center gap-2 text-sm text-muted-foreground"><UploadCloud className="size-4" aria-hidden="true" /> Click or drag a file here</p>
            }
          </div>
        </div>

        {/* Submit */}
        <Button type="submit" size="lg" className="w-full rounded-xl">
          Upload &amp; Index
        </Button>

        {/* Notice */}
        {notice && (
          <div className={[
            'rounded-lg p-3 text-sm content-fade',
            notice.type === 'success'
              ? 'bg-success/10 border border-success/30 text-success'
              : 'bg-destructive/10 border border-destructive/30 text-destructive',
          ].join(' ')}>
            {notice.type === 'success' && <strong>Queued: </strong>}
            {notice.msg}
          </div>
        )}
      </form>

      <p className="text-xs text-muted-foreground mt-4 text-center">
        Pipeline: extraction → cleaning → chunking → embedding → indexing → validation (FR-13)
      </p>
    </div>
  )
}
