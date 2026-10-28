/**
 * KnowledgePage — Core RAG chat interface (mock-ux.html §3. Knowledge Search).
 *
 * Features:
 * - Streaming answers from POST /query/stream (server-sent events): citations
 *   arrive first, then the answer grows token by token
 * - Citation markers in the answer link to source cards whose retrieved chunk
 *   text can be opened
 * - MorphOrb composer (21st.dev reference): the pill morphs into a thinking orb
 *   until retrieval returns, then the answer streams in the thread
 * - Interrupted / timed-out / stopped streams keep partial text and citations,
 *   are marked incomplete, and offer Retry
 * - Multi-turn conversation history (kept in App, one thread per client)
 * - Keyboard accessible; respects prefers-reduced-motion
 */
import { useState, useRef, useEffect, useCallback } from 'react'
import { AlertTriangle, Loader2, Lock, RotateCcw, Search, Square, X } from 'lucide-react'
import MorphOrb from '@/components/ui/ai-thiking-orb-and-input'
import { Button } from '@/components/ui/button'
import { readSSE } from '@/lib/sse'
import SourcePanel from './SourcePanel'

const API_BASE = import.meta.env.VITE_API_URL || '/api'
// Abort when no stream event arrives for this long (the stream itself may run longer).
const STREAM_IDLE_TIMEOUT_MS = Number(import.meta.env.VITE_STREAM_IDLE_TIMEOUT_MS) || 20000

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

/** Thrown for an `error` event sent by the server mid-stream. */
class ServerStreamError extends Error {}

/**
 * Open the streaming RAG endpoint and hand each event to onEvent, in order.
 * Resolves when the stream closes; rejects on HTTP/network/abort/parse errors.
 */
export async function streamRAG(question, clientId, signal, onEvent) {
  let res
  try {
    res = await fetch(`${API_BASE}/query/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ question, client_id: clientId || null, k: 5 }),
      signal,
    })
  } catch (err) {
    if (err.name === 'AbortError' || err.name === 'TimeoutError') throw err
    throw new Error('Network error — could not reach the RAG API. Check that the backend is running and try again.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(errorMessageFrom(body, res.status))
  }
  if (!res.body || !(res.headers.get('content-type') || '').includes('text/event-stream')) {
    throw new Error('The server did not return a stream.')
  }
  try {
    for await (const event of readSSE(res.body)) onEvent(event)
  } catch (err) {
    // A dropped connection surfaces as a TypeError from the reader.
    if (err instanceof TypeError) throw new Error('The connection dropped while the answer was streaming.')
    throw err
  }
}

// ------------------------------------------------------------------ //
// Answer text with linked citation markers                             //
// ------------------------------------------------------------------ //
const CITATION_RE = /(\[\d+\]|\[Source:[^\]]*\])/g

/** Index of the source a marker refers to, or -1 (never invent a link). */
function sourceIndexFor(marker, sources) {
  const byMarker = sources.findIndex(s => s.marker === marker)
  if (byMarker !== -1) return byMarker
  const doc = marker.match(/^\[Source:\s*([^,\]]+)/)?.[1]?.trim()
  return doc ? sources.findIndex(s => s.document_id === doc) : -1
}

function AnswerText({ text, sources, onCite }) {
  return text.split(CITATION_RE).map((part, i) => {
    if (i % 2 === 0) return part
    const idx = sourceIndexFor(part, sources)
    if (idx === -1) return part
    return (
      <button
        key={i}
        type="button"
        className="citation-marker"
        onClick={() => onCite(idx)}
        aria-label={`Open source ${part}: ${sources[idx].document_id}`}
      >
        {part}
      </button>
    )
  })
}

// ------------------------------------------------------------------ //
// Single conversation turn displayed in the history list              //
// ------------------------------------------------------------------ //
const QUESTION_BUBBLE = 'bg-primary text-primary-foreground rounded-2xl rounded-br-sm px-4 py-2.5 max-w-[80%] text-sm'
const ANSWER_CARD = 'bg-card border border-border rounded-2xl rounded-tl-sm px-5 py-4 max-w-[90%] text-sm leading-relaxed whitespace-pre-wrap'

function TurnCard({ turn, onRetry, onStop }) {
  const [openSources, setOpenSources] = useState(() => new Set())
  const idPrefix = `turn-${turn.id}-src`

  const toggleSource = i => setOpenSources(prev => {
    const next = new Set(prev)
    if (next.has(i)) next.delete(i); else next.add(i)
    return next
  })
  const openCitation = i => {
    setOpenSources(prev => new Set(prev).add(i))
    requestAnimationFrame(() => {
      const card = document.getElementById(`${idPrefix}-${i}`)
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
      card?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' })
      card?.querySelector('button')?.focus({ preventScroll: true })
    })
  }

  const streaming = turn.status === 'streaming'
  const hasAnswer = ['streaming', 'answered', 'incomplete'].includes(turn.status)

  return (
    <div className="space-y-3 answer-fade">
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className={QUESTION_BUBBLE}>{turn.question}</div>
      </div>

      {/* Waiting for retrieval (the orb overlay animates; this marks the turn) */}
      {turn.status === 'loading' && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Searching knowledge base…
        </div>
      )}

      {/* Streaming / answered / incomplete answer */}
      {hasAnswer && (
        <div className="flex flex-col gap-2">
          <div
            className={`${ANSWER_CARD} ${turn.status === 'incomplete' ? 'border-dashed border-warning/50' : ''}`}
            aria-busy={streaming}
          >
            {turn.status === 'incomplete' && (
              <span className="flex w-fit items-center gap-1 mb-2 text-xs font-medium text-warning">
                <AlertTriangle className="size-3.5" aria-hidden="true" /> Incomplete answer
              </span>
            )}
            {turn.answer
              ? <AnswerText text={turn.answer} sources={turn.sources} onCite={openCitation} />
              : streaming && <span className="text-muted-foreground">Sources retrieved — generating answer…</span>}
            {streaming && <span className="stream-caret" aria-hidden="true" />}
          </div>

          {streaming && (
            <div>
              <Button variant="outline" size="xs" className="rounded-full" onClick={onStop}>
                <Square data-icon="inline-start" /> Stop
              </Button>
            </div>
          )}

          {turn.status === 'incomplete' && (
            <div role="alert" className="bg-warning/10 border border-warning/30 rounded-xl px-4 py-3 max-w-[90%] text-sm text-warning flex items-start justify-between gap-3">
              <span>{turn.errorMsg} The partial answer and sources received so far are kept.</span>
              <Button variant="outline" size="xs" onClick={() => onRetry(turn.id)}>
                <RotateCcw data-icon="inline-start" /> Retry
              </Button>
            </div>
          )}

          <div className="max-w-[90%]">
            <SourcePanel
              sources={turn.sources}
              openSources={openSources}
              onToggle={toggleSource}
              idPrefix={idPrefix}
              emptyText={streaming ? 'Waiting for sources…' : 'No source evidence was returned for this answer.'}
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
              openSources={openSources}
              onToggle={toggleSource}
              idPrefix={idPrefix}
              title="Retrieved candidates — below relevance threshold, not used as evidence"
              emptyText="No candidate passages were retrieved."
            />
          </div>
        </div>
      )}

      {/* Error (nothing usable was received) */}
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
// Unique across module reloads: the thread outlives this module (it lives in App)
const newTurnId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`

function failureMessage(err) {
  if (err?.name === 'TimeoutError') return `The stream timed out (no data for ${Math.round(STREAM_IDLE_TIMEOUT_MS / 1000)} s).`
  return err?.message || 'The answer stopped streaming. Please retry.'
}

/**
 * Conversation history lives in App (keyed by client) so it survives page
 * navigation and never mixes evidence from different accounts.
 */
export default function KnowledgePage({ activeClient, onNavigate, turns, onTurnsChange }) {
  const [loading,  setLoading]      = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const loadingRef = useRef(false)
  const followRef = useRef(true) // keep the newest text in view until the user scrolls up
  const abortRef  = useRef(null)

  // Cancel an in-flight stream on unmount
  useEffect(() => () => abortRef.current?.abort(
    new DOMException('Request cancelled because you left Knowledge Search.', 'AbortError'),
  ), [])

  // Scrolling up stops following; scrolling back to the bottom resumes it
  useEffect(() => {
    let lastY = window.scrollY
    const onScroll = () => {
      const y = window.scrollY
      const atBottom = window.innerHeight + y >= document.documentElement.scrollHeight - 80
      if (y < lastY - 4 && !atBottom) followRef.current = false
      else if (atBottom) followRef.current = true
      lastY = y
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Follow the conversation as it grows (instant scroll: streaming updates are frequent)
  useEffect(() => {
    if (turns.length === 0 || !followRef.current) return
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'auto' })
  }, [turns])

  /**
   * Streams one question into the thread. Resolves (for the orb) as soon as
   * the stream's first real event arrives; the stream keeps updating the turn.
   */
  const doQuery = useCallback((q, retryId = null) => {
    if (!q.trim() || loadingRef.current) return Promise.resolve('cancelled')

    let settle
    const firstOutcome = new Promise(resolve => { settle = resolve })

    const controller = new AbortController()
    abortRef.current = controller
    let idleTimer
    const armIdleTimer = () => {
      clearTimeout(idleTimer)
      idleTimer = setTimeout(
        () => controller.abort(new DOMException('Stream timed out', 'TimeoutError')),
        STREAM_IDLE_TIMEOUT_MS,
      )
    }

    // Bind to the client at submit time so a late event lands in the right thread
    const setTurns = updater => onTurnsChange(activeClient, updater)
    const id = retryId ?? newTurnId()
    const update = patch => setTurns(prev => prev.map(t => (
      t.id === id ? { ...t, ...(typeof patch === 'function' ? patch(t) : patch) } : t
    )))

    loadingRef.current = true
    followRef.current = true
    setLoading(true)
    setAnnouncement('Searching knowledge base')

    // For retry: reset the failed turn in place; for a new question: append it
    const pendingTurn = { id, attempt: 0, question: q, status: 'loading', answer: '', sources: [], refusalReason: null, errorMsg: '' }
    if (retryId !== null) {
      setTurns(prev => prev.map(t => t.id === id ? { ...pendingTurn, attempt: (t.attempt || 0) + 1 } : t))
    } else {
      setTurns(prev => [...prev, pendingTurn])
    }

    const received = { answer: '', sources: 0 }
    let finished = false

    const onEvent = event => {
      armIdleTimer()
      switch (event.type) {
        case 'citations':
          if (!Array.isArray(event.sources)) throw new Error('The server sent malformed citations.')
          received.sources = event.sources.length
          update({ status: 'streaming', sources: event.sources })
          setAnnouncement(`${event.sources.length} sources retrieved. Answer streaming.`)
          settle('streaming')
          break
        case 'token':
          if (typeof event.text !== 'string') throw new Error('The server sent a malformed token.')
          received.answer += event.text
          update(t => ({ status: 'streaming', answer: t.answer + event.text }))
          settle('streaming')
          break
        case 'refusal':
          update({
            status: 'refused',
            answer: typeof event.message === 'string' ? event.message : '',
            refusalReason: event.reason || null,
            sources: Array.isArray(event.candidates) ? event.candidates : [],
          })
          setAnnouncement('Refused: insufficient evidence.')
          settle('refused')
          break
        case 'done':
          if (event.status === 'answered') {
            if (!received.answer.trim()) throw new Error('The stream finished without any answer text.')
            update({ status: 'answered' })
            setAnnouncement(`Answer complete with ${received.sources} sources.`)
          } else if (event.status !== 'refused') {
            throw new Error('The server sent an unknown completion status.')
          }
          finished = true
          break
        case 'error':
          throw new ServerStreamError(typeof event.message === 'string' ? event.message : 'The answer stopped streaming.')
        default:
          break // ignore unknown event types (forward compatible)
      }
    }

    ;(async () => {
      armIdleTimer()
      try {
        await streamRAG(q, activeClient, controller.signal, onEvent)
        if (!finished) throw new Error('The answer stream ended before completing.')
      } catch (err) {
        if (controller.signal.reason === CLEARED) { settle('cancelled'); return }
        const reason = controller.signal.aborted ? controller.signal.reason : err
        const message = failureMessage(reason)
        // Keep whatever arrived: partial text -> incomplete; nothing -> error
        update(t => (t.answer
          ? { status: 'incomplete', errorMsg: message }
          : { status: 'error', errorMsg: message, sources: [] }))
        setAnnouncement(received.answer ? `Answer interrupted. ${message}` : message)
        settle(reason?.name === 'AbortError' ? 'cancelled' : 'error')
      } finally {
        clearTimeout(idleTimer)
        loadingRef.current = false
        setLoading(false)
      }
    })()

    return firstOutcome
  }, [activeClient, onTurnsChange])

  const handleRetry  = (id) => {
    const failedQ = turns.find(t => t.id === id)?.question
    if (failedQ) doQuery(failedQ, id)
  }
  const stopStream = () => abortRef.current?.abort(new DOMException('Stopped by you.', 'AbortError'))
  const cancelQuery = () => abortRef.current?.abort(new DOMException('Request cancelled.', 'AbortError'))
  const clearHistory = () => {
    abortRef.current?.abort(CLEARED)
    onTurnsChange(activeClient, () => [])
    setAnnouncement('Conversation cleared.')
  }

  const hasHistory = turns.length > 0

  return (
    <div className="flex flex-col min-h-[calc(100vh-49px)]">
      {/* Screen-reader status: state changes only, not every streamed token */}
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>

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
            <TurnCard key={`${turn.id}:${turn.attempt || 0}`} turn={turn} onRetry={handleRetry} onStop={stopStream} />
          ))}
        </div>
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
      <MorphOrb
        onSubmit={doQuery}
        onCancel={cancelQuery}
        disabled={loading}
        placeholder={loading ? 'Answer streaming — press Stop to cancel' : undefined}
        maxLength={1000}
        minThinkMs={0}
        speed={1.5}
      />
    </div>
  )
}
