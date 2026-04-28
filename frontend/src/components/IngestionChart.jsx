// src/components/IngestionChart.jsx
import { useApiData } from '../hooks/useApi'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from 'recharts'
import { BarChart2 } from 'lucide-react'

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div
      className="panel px-3 py-2 text-xs"
      style={{ border: '1px solid var(--surface-4)', minWidth: 120 }}
    >
      <div className="mono mb-1.5" style={{ color: 'var(--text-2)' }}>{label}</div>
      {payload.map(p => (
        <div key={p.name} className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-sm" style={{ background: p.fill }} />
          <span style={{ color: 'var(--text-2)' }}>{p.name}:</span>
          <span className="mono ml-auto" style={{ color: 'var(--text-1)' }}>{p.value}</span>
        </div>
      ))}
    </div>
  )
}

export default function IngestionChart() {
  const { data: _icdata, loading } = useApiData('/dashboard/ingestion-timeline', {}, 120000)
  const data = _icdata || []

  // Format date label: "Jan 15" style
  const formatted = data.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  return (
    <div className="panel px-4 py-3 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <BarChart2 size={12} style={{ color: 'var(--amber)' }} />
        <span className="mono text-xs font-medium" style={{ color: 'var(--amber)' }}>
          INGESTION VOLUME — LAST 14 DAYS
        </span>
        <span className="ml-auto mono text-xs" style={{ color: 'var(--text-3)' }}>
          {data.reduce((s, d) => s + d.track_a + d.track_b, 0).toLocaleString()} total
        </span>
      </div>

      {loading && !data.length ? (
        <div className="h-32 flex items-center justify-center text-sm" style={{ color: 'var(--text-3)' }}>
          Loading…
        </div>
      ) : !data.length ? (
        <div className="h-32 flex items-center justify-center text-sm" style={{ color: 'var(--text-3)' }}>
          No data yet — run --once to start
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={140}>
          <BarChart data={formatted} barGap={2} barCategoryGap="30%">
            <CartesianGrid
              vertical={false}
              stroke="var(--surface-3)"
              strokeDasharray="3 3"
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: 'var(--text-3)', fontFamily: 'DM Mono, monospace' }}
              axisLine={false}
              tickLine={false}
              width={28}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
            <Legend
              wrapperStyle={{ fontSize: 10, fontFamily: 'DM Mono, monospace', color: 'var(--text-3)' }}
              formatter={v => v === 'track_a' ? 'Track A' : 'Track B'}
            />
            <Bar dataKey="track_a" name="track_a" fill="#4ade8066" radius={[2, 2, 0, 0]} stackId="a" />
            <Bar dataKey="track_b" name="track_b" fill="#60a5fa66" radius={[2, 2, 0, 0]} stackId="a" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
