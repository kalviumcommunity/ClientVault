/**
 * ThinkingOrb — Animated AI thinking indicator
 *
 * Inspired by 21st.dev ai-thiking-orb-and-input by @anark17r.
 * Implemented from scratch using CSS + React; no extra dependencies.
 * Respects prefers-reduced-motion via the global CSS rule in index.css.
 */
export default function ThinkingOrb() {
  return (
    <div className="flex flex-col items-center gap-5 py-16 answer-fade" role="status" aria-label="Searching knowledge base">
      {/* Outer glow wrapper */}
      <div className="relative flex items-center justify-center" style={{ width: 72, height: 72 }}>
        {/* Spinning conic-gradient ring */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: 'conic-gradient(from 0deg, #d946ef, #a78bfa, #38bdf8, #d946ef)',
            animation: 'spin-orb 2.4s linear infinite, glow-ring 2s ease-in-out infinite',
            borderRadius: '50%',
          }}
        />
        {/* White mask to create ring effect */}
        <div
          className="absolute rounded-full bg-slate-50"
          style={{ inset: 6 }}
        />
        {/* Pulsing core */}
        <div
          className="absolute rounded-full"
          style={{
            width: 22,
            height: 22,
            background: 'radial-gradient(circle at 35% 35%, #f0abfc, #d946ef)',
            animation: 'pulse-core 1.6s ease-in-out infinite',
          }}
        />
        {/* Orbiting particles */}
        {[
          { anim: 'orb-particle-1 2.4s linear infinite', color: '#d946ef' },
          { anim: 'orb-particle-2 2.4s linear infinite', color: '#a78bfa' },
          { anim: 'orb-particle-3 2.4s linear infinite', color: '#38bdf8' },
        ].map((p, i) => (
          <div
            key={i}
            className="absolute"
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: p.color,
              top: '50%',
              left: '50%',
              marginTop: -3,
              marginLeft: -3,
              animation: p.anim,
            }}
          />
        ))}
      </div>

      {/* Visual feedback only — the API does not report pipeline stages */}
      <p className="text-sm text-slate-500 font-medium animate-pulse">
        Searching knowledge base…
      </p>
    </div>
  )
}
