/**
 * SourcePanel — citation list for one answer.
 *
 * Each source shows its marker ([1]), document, chunk ID, section/page and
 * score; expanding it reveals the retrieved chunk text exactly as the API
 * returned it. Answer citation markers open and scroll to the matching card
 * (ids: `${idPrefix}-${index}`). No source fields are invented.
 */
import { ChevronRight, FileText } from 'lucide-react'

export default function SourcePanel({
  sources,
  openSources,
  onToggle,
  idPrefix,
  title = 'Sources',
  emptyText = 'No source evidence was returned for this answer.',
}) {
  if (!sources || sources.length === 0) {
    return (
      <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 text-xs text-warning content-fade">
        {emptyText}
      </div>
    )
  }

  return (
    <section className="content-fade" aria-label={title}>
      <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
        {title} ({sources.length})
      </p>
      <ol className="space-y-1.5">
        {sources.map((s, i) => {
          const isOpen = openSources.has(i)
          const docName = s.document_id?.split('/').pop() || s.document_id || 'document'
          const pct = typeof s.score === 'number' ? Math.round(s.score * 100) : null
          const location = [s.section, s.page != null ? `p. ${s.page}` : null].filter(Boolean).join(' · ')
          const cardId = `${idPrefix}-${i}`

          return (
            <li key={s.chunk_id || i} id={cardId} className="source-card" data-open={isOpen || undefined}>
              <button
                type="button"
                className="source-card-head"
                aria-expanded={isOpen}
                aria-controls={`${cardId}-text`}
                onClick={() => onToggle(i)}
              >
                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform source-chevron" aria-hidden="true" />
                <span className="font-mono font-medium text-violet-300 shrink-0">{s.marker}</span>
                <span className="min-w-0 flex-1 text-left">
                  <span className="block text-foreground font-medium truncate">{docName}</span>
                  <span className="block text-muted-foreground truncate">
                    <span className="font-mono">{s.chunk_id}</span>{location && <> · {location}</>}
                  </span>
                </span>
                {pct != null && <span className="score shrink-0">{pct}%</span>}
              </button>

              {isOpen && (
                <div id={`${cardId}-text`} className="source-card-body content-fade">
                  {typeof s.text === 'string' && s.text.trim()
                    ? (
                      <>
                        <p className="flex items-center gap-1.5 mb-1.5 text-muted-foreground">
                          <FileText className="size-3.5" aria-hidden="true" /> Retrieved chunk text
                        </p>
                        <blockquote className="source-text">{s.text}</blockquote>
                      </>
                    )
                    : <p className="text-muted-foreground">The API did not return text for this source.</p>
                  }
                  {typeof s.score === 'number' && (
                    <p className="mt-1.5 text-muted-foreground">Relevance score: {s.score.toFixed(4)}</p>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
