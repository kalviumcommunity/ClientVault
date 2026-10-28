/**
 * KnowledgePage — Core RAG chat interface (mock-ux.html §3. Knowledge Search).
 *
 * Features:
 * - MorphOrb composer (21st.dev reference): the pill morphs into a thinking orb
 *   while the real /query request runs; Escape cancels it
 * - Multi-turn conversation history (kept in App, one thread per client)
 * - Grounded answer display with expandable source evidence
 * - All UI states: idle, loading, answered, refused, error
 * - Keyboard accessible; respects prefers-reduced-motion
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { AlertTriangle, Loader2, Lock, RotateCcw, Search, X } from 'lucide-react'
import MorphOrb from '@/components/ui/ai-thiking-orb-and-input'
import { Button } from '@/components/ui/button'
import SourcePanel from './SourcePanel'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
const REQUEST_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS) || 30000
const KNOWN_STATUSES = ['answered', 'refused']

/** Turn a FastAPI error body into a readable message. 422 `detail` is an array. */
function errorMessageFrom(body, status) {
  const detail = body?.detail
  if (Array.isArray(detail)) {
    const msgs = detail.map(d => d?.msg).filter(Boolean)
    if (msgs.length) return `Invalid question: ${msgs.join('; ')}`
  }
  if (typeof detail === 'string' && detail) return `${detail} (HTTP ${status})`
  return `The RAG API is unavailable or failed to respond (HTTP ${status}). Try again.`
}

/**
 * Call the backend RAG endpoint.
 * @param {string} question
 * @param {string|null} clientId
 * @param {AbortSignal} signal
 * @returns {Promise<object>} parsed response body
 */
export async function queryRAG(question, clientId, signal) {
  let res
  try {
    res = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, client_id: clientId || null, k: 5 }),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError' || err.name === 'TimeoutError') throw err
    throw new Error('Network error — could not reach the RAG API. Check that the backend is running and try again.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(errorMessageFrom(body, res.status)), { isAPIError: true, status: res.status })
  }
  const data = await res.json().catch(() => null)
  if (!data || typeof data.answer !== 'string' || !KNOWN_STATUSES.includes(data.status) || !Array.isArray(data.sources)) {
    throw new Error('The server returned an empty or malformed response.')
  }
  return data
}

// ------------------------------------------------------------------ //
// Single conversation turn displayed in the history list              //
// ------------------------------------------------------------------ //
const QUESTION_BUBBLE = 'bg-primary text-primary-foreground rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[80%] text-sm'
const ANSWER_CARD = 'bg-card border border-border rounded-2xl rounded-tl-sm px-5 py-4 max-w-[90%] text-sm leading-relaxed whitespace-pre-wrap'

function TurnCard({ turn, onRetry }) {
  const [expandedSource, setExpandedSource] = useState(null)

  const toggleSource = i => setExpandedSource(prev => prev === i ? null : i)

  return (
    <div className="space-y-3 answer-fade">
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className={QUESTION_BUBBLE}>{turn.question}</div>
      </div>

      {/* Pending (the orb overlay animates; this marks the turn in the thread) */}
      {turn.status === 'loading' && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Searching knowledge base…
        </div>
      )}

      {/* Answer bubble */}
      {turn.status === 'answered' && turn.answer && (
        <div className="flex flex-col gap-2">
          <div className={ANSWER_CARD}>{turn.answer}</div>
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
            <div className={`${ANSWER_CARD} text-muted-foreground`}>{turn.answer}</div>
          )}
          {turn.refusalReason && (
            <div className="flex gap-2 bg-warning/10 border border-warning/30 rounded-lg p-3 text-xs text-warning max-w-[90%]">
              <AlertTriangle className="size-3.5 shrink-0 mt-px" aria-hidden="true" />
              <p><strong className="font-medium">Refusal reason:</strong> {turn.refusalReason}</p>
            </div>
          )}
          <div className="max-w-[90%]">
            <SourcePanel
              sources={turn.sources}
              expandedSource={expandedSource}
              onToggle={toggleSource}
              title="Retrieved candidates — below relevance threshold, not used as evidence"
              emptyText="No candidate passages were retrieved."
            />
          </div>
        </div>
      )}

      {/* Error */}
      {turn.status === 'error' && (
        <div role="alert" className="bg-destructive/10 border border-destructive/30 rounded-xl px-4 py-3 max-w-[90%] text-sm text-destructive flex items-start justify-between gap-3">
          <span>{turn.errorMsg}</span>
          <Button variant="destructive" size="xs" onClick={() => onRetry(turn.id)}>
            <RotateCcw data-icon="inline-start" /> Retry
          </Button>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ //
// Main page                                                            //
// ------------------------------------------------------------------ //
const CLEARED = 'cleared' // abort reason for an explicit "Clear conversation"
let nextTurnId = 1

/**
 * Conversation history lives in App (keyed by client) so it survives page
 * navigation and never mixes evidence from different accounts.
 */
export default function KnowledgePage({ activeClient, onNavigate, turns, onTurnsChange }) {
  const [loading,  setLoading]      = useState(false)
  const loadingRef = useRef(false)
  const bottomRef = useRef(null)
  const abortRef  = useRef(null)

  // Cancel an in-flight request on unmount
  useEffect(() => () => abortRef.current?.abort(
    new DOMException('Request cancelled because you left Knowledge Search.', 'AbortError'),
  ), [])

  // Scroll to bottom after each new turn
  useEffect(() => {
    if (turns.length > 0) {
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      bottomRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' })
    }
  }, [turns, loading])

  /** Runs one query and records it in the thread. Resolves with the outcome for the orb. */
  const doQuery = useCallback(async (q, retryId = null) => {
    if (!q.trim() || loadingRef.current) return 'cancelled'

    const controller = new AbortController()
    abortRef.current = controller
    const timer = setTimeout(
      () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
      REQUEST_TIMEOUT_MS,
    )

    // Bind to the client at submit time so a late response lands in the right thread
    const setTurns = updater => onTurnsChange(activeClient, updater)
    const id = retryId ?? nextTurnId++
    const replaceTurn = turn => setTurns(prev => prev.map(t => t.id === id ? { ...turn, id } : t))

    loadingRef.current = true
    setLoading(true)

    // For retry: replace the failed turn in place; for a new question: append a pending turn
    const pendingTurn = { id, question: q, status: 'loading', answer: '', sources: [], refusalReason: null, errorMsg: '' }
    if (retryId !== null) {
      replaceTurn(pendingTurn)
    } else {
      setTurns(prev => [...prev, pendingTurn])
    }

    try {
      const data = await queryRAG(q, activeClient, controller.signal)
      replaceTurn({
        question: q,
        status: data.status,
        answer: data.answer || '',
        sources: data.sources,
        refusalReason: data.refusal_reason || null,
        errorMsg: '',
      })
      return data.status
    } catch (err) {
      if (controller.signal.reason === CLEARED) return 'cancelled' // conversation was cleared

      replaceTurn({
        question: q,
        status: 'error',
        answer: '',
        sources: [],
        refusalReason: null,
        errorMsg: err.name === 'TimeoutError'
          ? 'Request timed out. Check your connection and try again.'
          : err.message || 'Network error. Please try again.',
      })
      return err.name === 'AbortError' ? 'cancelled' : 'error'
    } finally {
      clearTimeout(timer)
      loadingRef.current = false
      setLoading(false)
    }
  }, [activeClient, onTurnsChange])

  const handleRetry  = (id) => {
    const failedQ = turns.find(t => t.id === id)?.question
    if (failedQ) doQuery(failedQ, id)
  }
  const cancelQuery = () => abortRef.current?.abort(new DOMException('Request cancelled.', 'AbortError'))
  const clearHistory = () => {
    abortRef.current?.abort(CLEARED)
    onTurnsChange(activeClient, () => [])
  }

  const hasHistory = turns.length > 0

  return (
    <div className="flex flex-col min-h-[calc(100vh-49px)]">
      {/* ---- Page header ---- */}
      <div className="px-4 pt-6 pb-2 max-w-3xl mx-auto w-full">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-lg font-semibold">Knowledge Search</h1>
            <p className="text-xs text-muted-foreground">
              {activeClient
                ? <>Account-locked: <span className="font-mono font-medium text-violet-300">{activeClient}</span></>
                : <>No client selected — <button onClick={() => onNavigate('clients')} className="text-violet-300 underline underline-offset-2">select one</button></>
              }
            </p>
          </div>
          {hasHistory && (
            <Button variant="outline" size="sm" className="rounded-full" onClick={clearHistory}>
              <X data-icon="inline-start" /> Clear conversation
            </Button>
          )}
        </div>
      </div>

      {/* ---- Conversation area ---- */}
      <main
        className="flex-1 px-4 pb-56 pt-4 max-w-3xl mx-auto w-full"
        id="conversation"
        aria-live="polite"
        aria-label="Conversation"
      >
        {/* Empty / idle state */}
        {!hasHistory && (
          <div className="flex flex-col items-center justify-center min-h-[300px] text-center content-fade">
            <div className="size-12 rounded-full mb-5 grid place-items-center border border-border bg-card" aria-hidden="true">
              <Search className="size-5 text-muted-foreground" />
            </div>
            <h2 className="text-xl font-semibold mb-2">What would you like to know?</h2>
            <p className="text-muted-foreground text-sm max-w-sm">
              Ask about procedures, SLAs, runbooks, or client policies.
              {activeClient && <> Results are scoped to <strong className="font-medium text-violet-300">{activeClient}</strong>.</>}
            </p>
            {!activeClient && (
              <p className="flex items-center gap-1.5 text-xs text-warning mt-3 bg-warning/10 border border-warning/30 rounded-lg px-3 py-2">
                <AlertTriangle className="size-3.5" aria-hidden="true" />
                No client selected. Results will be unfiltered.
                <button onClick={() => onNavigate('clients')} className="underline underline-offset-2 font-medium">Select a client →</button>
              </p>
            )}
          </div>
        )}

        {/* Conversation turns */}
        <div className="space-y-6">
          {turns.map(turn => (
            <TurnCard key={turn.id} turn={turn} onRetry={handleRetry} />
          ))}
        </div>
        <div ref={bottomRef} />
      </main>

      {/* ---- Composer: fade + scope chip + disclaimer around the MorphOrb pill ---- */}
      <div className="fixed inset-x-0 bottom-0 h-48 bg-linear-to-t from-background via-background/95 to-transparent pointer-events-none z-10" aria-hidden="true" />
      {activeClient && (
        <div className="fixed inset-x-0 bottom-[138px] flex justify-center pointer-events-none z-20">
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground bg-card border border-border rounded-full px-3 py-0.5">
            <Lock className="size-3" aria-hidden="true" /> Scoped to <strong className="font-medium text-violet-300">{activeClient}</strong>
          </span>
        </div>
      )}
      <p className="fixed inset-x-0 bottom-5 px-4 text-center text-xs text-muted-foreground z-20 pointer-events-none">
        Answers are grounded in retrieved documents only. Unverifiable questions return an explicit refusal.
      </p>
      <MorphOrb onSubmit={doQuery} onCancel={cancelQuery} maxLength={1000} />
    </div>
  )
}
