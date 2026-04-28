// src/components/SourceBreakdown.jsx
import { useApiData } from '../hooks/useApi'
import { Layers } from 'lucide-react'

const PALETTE = [
  '#f59e0b', '#60a5fa', '#4ade80', '#a78bfa',
  '#f87171', '#34d399', '#fb923c', '#e879f9',
  '#38bdf8', '#facc15', '#94a3b8', '#f472b6',
  '#2dd4bf', '#c084fc', '#fb7185',
]

export default function SourceBreakdown() {
  const { data: _sbdata, loading } = useApiData('/dashboard/feed-summary', {}, 120000)
  const data = _sbdata || []
  const total = data.reduce((s, d) => s + d.count, 0)

  return (
    <div className="panel px-4 py-3 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Layers size={12} style={{ color: 'var(--amber)' }} />
        <span className="mono text-xs font-medium" style={{ color: 'var(--amber)' }}>
          TOP SOURCES
        </span>
        <span className="ml-auto mono text-xs" style={{ color: 'var(--text-3)' }}>
          {total.toLocaleString()} articles
        </span>
      </div>

      {loading && !data.length ? (
        <div className="h-20 flex items-center justify-center text-sm" style={{ color: 'var(--text-3)' }}>
          Loading…
        </div>
      ) : !data.length ? (
        <div className="h-20 flex items-center justify-center text-sm" style={{ color: 'var(--text-3)' }}>
          No data yet
        </div>
      ) : (
        <div className="space-y-2">
          {data.slice(0, 10).map((s, i) => {
            const pct = total > 0 ? (s.count / total) * 100 : 0
            const color = PALETTE[i % PALETTE.length]
            return (
              <div key={s.domain} className="flex items-center gap-2">
                <span
                  className="mono text-xs truncate flex-1"
                  style={{ color: 'var(--text-2)', minWidth: 0 }}
                >
                  {s.domain}
                </span>
                <div
                  className="h-1.5 rounded-full"
                  style={{ width: `${Math.max(pct, 2)}%`, maxWidth: 80, background: color, opacity: 0.8, minWidth: 4 }}
                />
                <span className="mono text-xs shrink-0" style={{ color: 'var(--text-3)', width: 28, textAlign: 'right' }}>
                  {s.count}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
