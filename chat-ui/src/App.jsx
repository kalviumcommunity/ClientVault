import React, { useState, useRef, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

export default function App() {
  const [question, setQuestion] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | answered | refused | error
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState([])
  const [refusalReason, setRefusalReason] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [expandedSource, setExpandedSource] = useState(null)
  const inputRef = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  const submit = async () => {
    const q = question.trim()
    if (!q) return
    setStatus('loading')
    setAnswer('')
    setSources([])
    setRefusalReason(null)
    setErrorMsg('')
    setExpandedSource(null)

    try {
      const res = await fetch(`${API_BASE}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, client_id: 'NEXUS-002', k: 5 }),
        signal: AbortSignal.timeout(30000)
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setStatus('error')
        setErrorMsg(body.detail || `Server error (${res.status})`)
        return
      }
      const data = await res.json()
      setAnswer(data.answer || '')
      setSources(data.sources || [])
      setRefusalReason(data.refusal_reason || null)
      setStatus(data.status === 'refused' ? 'refused' : 'answered')
    } catch (err) {
      setStatus('error')
      setErrorMsg(err.name === 'TimeoutError' ? 'Request timed out. Please try again.' : `Network error: ${err.message}`)
    }
  }

  const handleKeyDown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }
  const newQuestion = () => { setQuestion(''); setStatus('idle'); setAnswer(''); setSources([]); setRefusalReason(null); setErrorMsg(''); inputRef.current?.focus() }

  const navLinks = ['Dashboard', 'Clients', 'Knowledge', 'Documents', 'Upload']

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Top Navigation - from mock-ux.html */}
      <header className="bg-slate-900 text-white px-4 py-3 flex items-center gap-4 flex-wrap">
        <span className="font-extrabold tracking-wide text-sm"><span className="text-fuchsia-400">CLIENT</span>VAULT</span>
        {navLinks.map(l => (
          <span key={l} className={`text-xs font-semibold px-3 py-1.5 rounded-md ${l === 'Knowledge' ? 'bg-fuchsia-500 text-white' : 'border border-white/30 text-white/70'}`}>{l}</span>
        ))}
        <span className="flex-1" />
        <span className="text-xs border border-white/30 rounded px-2 py-1 text-white/60">NEXUS-002</span>
      </header>

      {/* Main Chat Area */}
      <main className="max-w-3xl mx-auto px-4 pt-12 pb-24">
        {status === 'idle' && (
          <div className="text-center pt-20">
            <h2 className="text-2xl font-bold text-slate-800 mb-2">What would you like to know?</h2>
            <p className="text-slate-500 text-sm">Ask about procedures, SLAs, runbooks, or client policies.</p>
          </div>
        )}

        {status === 'loading' && (
          <div className="flex flex-col items-center gap-4 py-16 answer-fade">
            <div className="thinking-orb"><div className="thinking-orb-inner" /></div>
            <p className="text-slate-500 text-sm animate-pulse">Searching knowledge base...</p>
          </div>
        )}

        {(status === 'answered' || status === 'refused') && answer && (
          <div className="answer-fade space-y-4">
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <p className="text-sm font-semibold text-slate-400 mb-1">Q: {question}</p>
              <div className="prose prose-slate max-w-none text-sm leading-relaxed whitespace-pre-wrap">{answer}</div>
            </div>

            {sources.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-slate-400 mb-2">SOURCES ({sources.length})</p>
                <div className="flex flex-wrap gap-2">
                  {sources.map((s, i) => (
                    <div key={i} className="source-chip" onClick={() => setExpandedSource(expandedSource === i ? null : i)}>
                      <span className="font-medium">{s.marker}</span> {s.document_id?.split('/').pop() || 'doc'}
                      <span className="score ml-2">{s.score?.toFixed(3)}</span>
                      {expandedSource === i && (
                        <div className="mt-2 pt-2 border-t border-slate-200 text-xs text-slate-600">
                          <div>chunk: {s.chunk_id}</div>
                          <div>section: {s.section}</div>
                          <div>page: {s.page}</div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {status === 'refused' && refusalReason && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800">{refusalReason}</div>
            )}

            <button onClick={newQuestion} className="text-sm text-fuchsia-600 hover:text-fuchsia-800 font-medium transition-colors">← Ask a new question</button>
          </div>
        )}

        {status === 'error' && (
          <div className="answer-fade text-center py-12">
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4 text-sm text-red-700">{errorMsg}</div>
            <button onClick={submit} className="text-sm text-fuchsia-600 hover:text-fuchsia-800 font-medium mr-4">↻ Retry</button>
            <button onClick={newQuestion} className="text-sm text-slate-500 hover:text-slate-700 font-medium">← Ask a new question</button>
          </div>
        )}
      </main>

      {/* Sticky pill input */}
      <div className="fixed bottom-0 left-0 right-0 bg-gradient-to-t from-slate-50 via-slate-50/95 to-transparent pt-8 pb-4 px-4">
        <div className="max-w-2xl mx-auto flex items-center gap-2 bg-white border border-slate-200 rounded-full shadow-lg px-4 py-2 focus-within:ring-2 focus-within:ring-fuchsia-400 focus-within:border-fuchsia-300 transition-all">
          <input ref={inputRef} type="text" value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="Ask about a procedure, SLA, or runbook..."
            className="flex-1 outline-none text-sm bg-transparent py-2"
            disabled={status === 'loading'} aria-label="Question input" />
          <button onClick={submit} disabled={status === 'loading' || !question.trim()}
            className="bg-fuchsia-500 hover:bg-fuchsia-600 disabled:bg-slate-300 text-white rounded-full px-5 py-1.5 text-sm font-semibold transition-colors"
            aria-label="Submit question">
            {status === 'loading' ? '...' : 'Ask'}
          </button>
        </div>
      </div>
    </div>
  )
}
