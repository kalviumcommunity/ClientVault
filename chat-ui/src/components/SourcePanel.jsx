/**
 * SourcePanel — Expandable source-evidence display.
 *
 * Renders source chips returned by the RAG API. Each chip is keyboard-
 * accessible. Expanding a chip reveals chunk_id, section, page, and score.
 * No source fields are invented; only what the API returns is shown.
 */
export default function SourcePanel({
  sources,
  expandedSource,
  onToggle,
  title = 'Sources',
  emptyText = 'No source evidence was returned for this answer.',
}) {
  if (!sources || sources.length === 0) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-700 content-fade">
        {emptyText}
      </div>
    )
  }

  return (
    <div className="content-fade">
      <p className="text-xs font-semibold text-slate-400 mb-2 uppercase tracking-wide">
        {title} ({sources.length})
      </p>
      <div className="flex flex-wrap items-start gap-2">
        {sources.map((s, i) => {
          const isOpen = expandedSource === i
          const docName = s.document_id?.split('/').pop() || s.document_id || 'document'
          const pct = s.score != null ? Math.round(s.score * 100) : null

          return (
            <div
              key={i}
              className="source-chip"
              role="button"
              tabIndex={0}
              aria-expanded={isOpen}
              aria-label={`Source ${i + 1}: ${docName}${pct != null ? `, ${pct}% match` : ''}`}
              onClick={() => onToggle(i)}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(i) }
              }}
            >
              {/* Chip header row */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-semibold text-fuchsia-600">{s.marker}</span>
                <span className="text-slate-700 font-medium">{docName}</span>
                {pct != null && (
                  <span className="score ml-auto">
                    {pct}%
                  </span>
                )}
              </div>

              {/* Expanded detail */}
              {isOpen && (
                <div className="mt-2 pt-2 border-t border-slate-200 text-xs text-slate-600 space-y-1 content-fade">
                  {s.chunk_id  && <div><span className="font-medium text-slate-500">Chunk:</span> {s.chunk_id}</div>}
                  {s.section   && <div><span className="font-medium text-slate-500">Section:</span> {s.section}</div>}
                  {s.page != null && <div><span className="font-medium text-slate-500">Page:</span> {s.page}</div>}
                  {s.score != null && <div><span className="font-medium text-slate-500">Score:</span> {s.score.toFixed(4)}</div>}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
