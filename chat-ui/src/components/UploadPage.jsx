/**
 * UploadPage — Document Upload & Indexing (mock-ux.html §5).
 * Admin screen — accepts file + client + doc type metadata.
 * No actual upload backend is connected; shows the PRD-specified UI states.
 */
import { useState } from 'react'

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
        <h1 className="text-xl font-bold text-slate-800">Document Upload &amp; Indexing</h1>
        <p className="text-sm text-slate-500 mt-1">Admin workflow — add or re-index corpus documents (FR-12, FR-13).</p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4 bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        {/* Client selector */}
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1" htmlFor="upload-client">
            Client account <span className="text-red-500">*</span>
          </label>
          <select
            id="upload-client"
            value={client}
            onChange={e => setClient(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-400"
          >
            {CLIENTS.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>

        {/* Doc type */}
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1" htmlFor="upload-doctype">
            Document type
          </label>
          <select
            id="upload-doctype"
            value={docType}
            onChange={e => setDocType(e.target.value)}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-fuchsia-400"
          >
            {DOC_TYPES.map(t => <option key={t}>{t}</option>)}
          </select>
        </div>

        {/* File dropzone */}
        <div>
          <label className="block text-xs font-semibold text-slate-600 mb-1" htmlFor="upload-file">
            File <span className="text-red-500">*</span> <span className="text-slate-400 font-normal">(PDF · DOCX · TXT · MD · HTML)</span>
          </label>
          <div className="relative border-2 border-dashed border-slate-300 rounded-xl p-6 text-center hover:border-fuchsia-400 transition-colors">
            <input
              id="upload-file"
              type="file"
              accept=".pdf,.docx,.txt,.md,.html"
              className="absolute inset-0 opacity-0 cursor-pointer"
              onChange={e => { setFile(e.target.files?.[0] || null); setNotice(null) }}
            />
            {file
              ? <p className="text-sm font-medium text-fuchsia-600">{file.name}</p>
              : <p className="text-sm text-slate-400">⬆ Click or drag a file here</p>
            }
          </div>
        </div>

        {/* Submit */}
        <button
          type="submit"
          className="w-full bg-fuchsia-500 hover:bg-fuchsia-600 disabled:bg-slate-300 text-white font-semibold py-2.5 rounded-xl transition-colors focus-visible:outline-2 focus-visible:outline-fuchsia-400"
        >
          Upload &amp; Index
        </button>

        {/* Notice */}
        {notice && (
          <div className={[
            'rounded-lg p-3 text-sm content-fade',
            notice.type === 'success'
              ? 'bg-emerald-50 border border-emerald-200 text-emerald-800'
              : 'bg-red-50 border border-red-200 text-red-700',
          ].join(' ')}>
            {notice.type === 'success' && <strong>Queued: </strong>}
            {notice.msg}
          </div>
        )}
      </form>

      <p className="text-xs text-slate-400 mt-4 text-center">
        Pipeline: extraction → cleaning → chunking → embedding → indexing → validation (FR-13)
      </p>
    </div>
  )
}
