// src/components/CountryRiskTable.jsx
import { useState } from 'react'
import { useApiData } from '../hooks/useApi'
import { Globe } from 'lucide-react'

const CAT_COLOR = {
  critical: '#ef4444',
  high:     '#f97316',
  moderate: '#eab308',
  stable:   '#22c55e',
}

const CAT_ORDER = { critical: 0, high: 1, moderate: 2, stable: 3 }

export default function CountryRiskTable() {
  const { data: _crdata, loading } = useApiData('/dashboard/country-risk', {}, 300000)
  const data = _crdata || []
  const [filter, setFilter] = useState('all')

  const FILTERS = ['all', 'critical', 'high', 'moderate', 'stable']

  const filtered = filter === 'all'
    ? data
    : data.filter(r => r.risk_category === filter)

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'var(--surface-3)' }}>
        <Globe size={12} style={{ color: 'var(--amber)' }} />
        <span className="mono text-xs font-medium" style={{ color: 'var(--amber)' }}>
          COUNTRY RISK INDEX
        </span>

        <div className="flex gap-0.5 ml-auto">
          {FILTERS.map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="px-2 py-0.5 text-xs rounded mono transition-all capitalize"
              style={{
                background: filter === f ? 'var(--surface-3)' : 'transparent',
                color: filter === f
                  ? (f === 'all' ? 'var(--amber)' : CAT_COLOR[f])
                  : 'var(--text-3)',
              }}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-y-auto flex-1">
        {loading && (
          <div className="flex items-center justify-center h-20 text-sm" style={{ color: 'var(--text-3)' }}>
            Loading…
          </div>
        )}

        <table className="w-full text-xs">
          <thead className="sticky top-0" style={{ background: 'var(--surface-2)' }}>
            <tr>
              {['Country', 'Code', 'Score', 'Category', 'Notes'].map(h => (
                <th
                  key={h}
                  className="px-4 py-2 text-left mono font-medium"
                  style={{ color: 'var(--text-3)' }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(r => (
              <tr
                key={r.country_code}
                style={{ borderTop: "1px solid var(--surface-3)" }}
                style={{ borderColor: 'var(--surface-3)' }}
              >
                <td className="px-4 py-2" style={{ color: 'var(--text-1)' }}>
                  {r.country_name}
                </td>
                <td className="px-4 py-2 mono" style={{ color: 'var(--text-3)' }}>
                  {r.country_code}
                </td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <div className="w-16 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--surface-3)' }}>
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${r.risk_score}%`,
                          background: CAT_COLOR[r.risk_category] || '#6b7280',
                        }}
                      />
                    </div>
                    <span className="mono" style={{ color: CAT_COLOR[r.risk_category] }}>
                      {r.risk_score}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-2">
                  <span
                    className="tag capitalize"
                    style={{
                      background: `${CAT_COLOR[r.risk_category]}18`,
                      color: CAT_COLOR[r.risk_category],
                      border: `1px solid ${CAT_COLOR[r.risk_category]}40`,
                    }}
                  >
                    {r.risk_category}
                  </span>
                </td>
                <td className="px-4 py-2" style={{ color: 'var(--text-3)', maxWidth: 200 }}>
                  <span className="truncate block">{r.notes}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
