/**
 * KnowledgePage — Core RAG chat interface (mock-ux.html §3. Knowledge Search).
 *
 * Features:
 * - Premium animated thinking orb (21st.dev reference visual style)
 * - Pill-shaped input with sticky bottom placement
 * - Multi-turn conversation history
 * - Grounded answer display with expandable source evidence
 * - All UI states: idle, loading, answered, refused, error
 * - Keyboard accessible; respects prefers-reduced-motion via CSS
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import ThinkingOrb from './ThinkingOrb'
import SourcePanel from './SourcePanel'

const API_BASE = import.meta.env.VITE_API_URL || '/api'

/**
 * Call the backend RAG endpoint.
 * @param {string} question
 * @param {string|null} clientId
 * @param {AbortSignal} signal
 * @returns {Promise<object>} parsed response body
 */
async function queryRAG(question, clientId, signal) {
  const res = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, client_id: clientId || null, k: 5 }),
    signal,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(body.detail || `Server error (${res.status})`), { isAPIError: true, status: res.status })
  }
  const data = await res.json()
  if (!data || typeof data.answer !== 'string') {
    throw new Error('Unexpected response format from server.')
  }
  return data
}

// ------------------------------------------------------------------ //
// Single conversation turn displayed in the history list              //
// ------------------------------------------------------------------ //
function TurnCard({ turn, index, onRetry }) {
  const [expandedSource, setExpandedSource] = useState(null)

  const toggleSource = i => setExpandedSource(prev => prev === i ? null : i)

  return (
    <div className="space-y-3 answer-fade">
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className="bg-fuchsia-500 text-white rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[80%] text-sm shadow-sm">
          {turn.question}
        </div>
      </div>

      {/* Answer bubble */}
      {turn.status === 'answered' && turn.answer && (
        <div className="flex flex-col gap-2">
          <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm max-w-[90%]">
            <div className="prose prose-slate max-w-none text-sm leading-relaxed whitespace-pre-wrap">
              {turn.answer}
            </div>
          </div>
          {/* Sources */}
          <div className="max-w-[90%]">
            <SourcePanel
              sources={turn.sources}
              expandedSource={expandedSource}
              onToggle={toggleSource}
            />
          </div>
        </div>
      )}

      {/* Refusal */}
      {turn.status === 'refused' && (
        <div className="flex flex-col gap-2">
          {turn.answer && (
            <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm max-w-[90%] text-sm leading-relaxed whitespace-pre-wrap text-slate-700">
              {turn.answer}
            </div>
          )}
          {turn.refusalReason && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 max-w-[90%]">
              <strong>Refusal reason:</strong> {turn.refusalReason}
            </div>
          )}
          <div className="max-w-[90%]">
            <SourcePanel sources={turn.sources} expandedSource={expandedSource} onToggle={toggleSource} />
          </div>
        </div>
      )}

      {/* Error */}
      {turn.status === 'error' && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 max-w-[90%] text-sm text-red-700 flex items-start justify-between gap-3">
          <span>{turn.errorMsg}</span>
          <button
            onClick={() => onRetry(index)}
            className="shrink-0 text-xs font-semibold text-red-700 hover:text-red-900 underline underline-offset-2"
          >
            ↻ Retry
          </button>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ //
// Main page                                                            //
// ------------------------------------------------------------------ //
export default function KnowledgePage({ activeClient, onNavigate }) {
  const [question, setQuestion]     = useState('')
  const [turns,    setTurns]        = useState([])    // conversation history
  const [loading,  setLoading]      = useState(false)
  const inputRef  = useRef(null)
  const bottomRef = useRef(null)
  const abortRef  = useRef(null)

  // Auto-focus input on mount
  useEffect(() => { inputRef.current?.focus() }, [])

  // Scroll to bottom after each new turn
  useEffect(() => {
    if (turns.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [turns, loading])

  const doQuery = useCallback(async (q, retryIndex = null) => {
    if (!q.trim() || loading) return

    // Cancel any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)

    // For retry: replace the failed turn; for new question: add a pending turn
    const pendingTurn = { question: q, status: 'loading', answer: '', sources: [], refusalReason: null, errorMsg: '' }

    if (retryIndex !== null) {
      setTurns(prev => prev.map((t, i) => i === retryIndex ? pendingTurn : t))
    } else {
      setTurns(prev => [...prev, pendingTurn])
      setQuestion('')
    }

    try {
      const data = await queryRAG(q, activeClient, controller.signal)
      const completedTurn = {
        question: q,
        status: data.status === 'refused' ? 'refused' : 'answered',
        answer: data.answer || '',
        sources: data.sources || [],
        refusalReason: data.refusal_reason || null,
        errorMsg: '',
      }

      if (retryIndex !== null) {
        setTurns(prev => prev.map((t, i) => i === retryIndex ? completedTurn : t))
      } else {
        setTurns(prev => [...prev.slice(0, -1), completedTurn])
      }
    } catch (err) {
      if (err.name === 'AbortError') return // cancelled — do nothing

      const errorTurn = {
        question: q,
        status: 'error',
        answer: '',
        sources: [],
        refusalReason: null,
        errorMsg: err.name === 'TimeoutError'
          ? 'Request timed out. Check your connection and try again.'
          : err.message || 'Network error. Please try again.',
      }
      if (retryIndex !== null) {
        setTurns(prev => prev.map((t, i) => i === retryIndex ? errorTurn : t))
      } else {
        setTurns(prev => [...prev.slice(0, -1), errorTurn])
      }
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }, [activeClient, loading])

  const handleSubmit = () => doQuery(question)
  const handleRetry  = (index) => {
    const failedQ = turns[index]?.question
    if (failedQ) doQuery(failedQ, index)
  }
  const handleKeyDown = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }
  const clearHistory = () => {
    abortRef.current?.abort()
    setTurns([])
    setLoading(false)
    setQuestion('')
    inputRef.current?.focus()
  }

  const hasHistory = turns.length > 0

  return (
    <div className="flex flex-col min-h-[calc(100vh-48px)]">
      {/* ---- Page header ---- */}
      <div className="px-4 pt-6 pb-2 max-w-3xl mx-auto w-full">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-lg font-bold text-slate-800">Knowledge Search</h1>
            <p className="text-xs text-slate-500">
              {activeClient
                ? <>Account-locked: <span className="font-mono font-semibold text-fuchsia-600">{activeClient}</span></>
                : <>No client selected — <button onClick={() => onNavigate('clients')} className="text-fuchsia-600 underline">select one</button></>
              }
            </p>
          </div>
          {hasHistory && (
            <button
              onClick={clearHistory}
              className="text-xs text-slate-500 hover:text-slate-700 border border-slate-300 rounded-full px-3 py-1 transition-colors"
            >
              ✕ Clear conversation
            </button>
          )}
        </div>
      </div>

      {/* ---- Conversation area ---- */}
      <main
        className="flex-1 overflow-y-auto px-4 pb-32 pt-4 max-w-3xl mx-auto w-full"
        id="conversation"
        aria-live="polite"
        aria-label="Conversation"
      >
        {/* Empty / idle state */}
        {!hasHistory && !loading && (
          <div className="flex flex-col items-center justify-center min-h-[300px] text-center content-fade">
            <div
              className="w-14 h-14 rounded-full mb-5 flex items-center justify-center"
              style={{ background: 'conic-gradient(from 0deg, #d946ef, #a78bfa, #d946ef)', opacity: 0.85 }}
              aria-hidden="true"
            >
              <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center">
                <span className="text-lg">🔍</span>
              </div>
            </div>
            <h2 className="text-xl font-bold text-slate-700 mb-2">What would you like to know?</h2>
            <p className="text-slate-400 text-sm max-w-sm">
              Ask about procedures, SLAs, runbooks, or client policies.
              {activeClient && <> Results are scoped to <strong className="text-fuchsia-600">{activeClient}</strong>.</>}
            </p>
            {!activeClient && (
              <p className="text-xs text-amber-600 mt-3 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                ⚠ No client selected. Results will be unfiltered.{' '}
                <button onClick={() => onNavigate('clients')} className="underline font-semibold">Select a client →</button>
              </p>
            )}
          </div>
        )}

        {/* Conversation turns */}
        <div className="space-y-6">
          {turns.map((turn, i) => (
            turn.status === 'loading'
              ? (
                <div key={i}>
                  <div className="flex justify-end mb-3">
                    <div className="bg-fuchsia-500 text-white rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[80%] text-sm shadow-sm">
                      {turn.question}
                    </div>
                  </div>
                  <ThinkingOrb />
                </div>
              )
              : (
                <TurnCard key={i} turn={turn} index={i} onRetry={handleRetry} />
              )
          ))}
        </div>
        <div ref={bottomRef} />
      </main>

      {/* ---- Sticky pill input ---- */}
      <div className="fixed bottom-0 left-0 right-0 bg-gradient-to-t from-slate-50 via-slate-50/98 to-transparent pt-10 pb-4 px-4 pointer-events-none">
        <div className="max-w-2xl mx-auto pointer-events-auto">
          {/* Active client hint strip */}
          {activeClient && (
            <div className="flex justify-center mb-2">
              <span className="text-xs text-slate-500 bg-white border border-slate-200 rounded-full px-3 py-0.5 shadow-sm">
                🔒 Scoped to <strong className="text-fuchsia-600">{activeClient}</strong>
              </span>
            </div>
          )}

          <div
            className={[
              'flex items-center gap-2 bg-white border rounded-full shadow-lg px-4 py-2 transition-all duration-200',
              'focus-within:ring-2 focus-within:ring-fuchsia-400 focus-within:border-fuchsia-300',
              loading ? 'border-fuchsia-300 ring-2 ring-fuchsia-100' : 'border-slate-200',
            ].join(' ')}
            role="search"
          >
            <input
              ref={inputRef}
              type="text"
              value={question}
              onChange={e => setQuestion(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={loading ? 'Searching…' : 'Ask about a procedure, SLA, or runbook…'}
              className="flex-1 outline-none text-sm bg-transparent py-2 placeholder-slate-400"
              disabled={loading}
              aria-label="Question input"
              aria-describedby={activeClient ? 'client-scope-hint' : undefined}
              maxLength={1000}
            />
            {/* Character count when approaching limit */}
            {question.length > 800 && (
              <span className="text-xs text-slate-400 shrink-0">{1000 - question.length}</span>
            )}
            <button
              onClick={handleSubmit}
              disabled={loading || !question.trim()}
              className={[
                'shrink-0 rounded-full px-5 py-1.5 text-sm font-semibold transition-all duration-150',
                'focus-visible:outline-2 focus-visible:outline-fuchsia-400',
                loading || !question.trim()
                  ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  : 'bg-fuchsia-500 hover:bg-fuchsia-600 active:scale-95 text-white shadow-sm',
              ].join(' ')}
              aria-label={loading ? 'Request in progress' : 'Submit question'}
            >
              {loading ? (
                <span className="flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  …
                </span>
              ) : 'Ask'}
            </button>
          </div>
          <p className="text-center text-xs text-slate-400 mt-2">
            Answers are grounded in retrieved documents only. Unverifiable questions return an explicit refusal.
          </p>
        </div>
      </div>
    </div>
  )
}
