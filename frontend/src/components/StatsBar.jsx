// src/components/StatsBar.jsx
import { useApiData } from '../hooks/useApi'
import { fmtNum, timeAgo } from '../utils'
import { Activity, Database, AlertTriangle, Shield, Rss, Clock } from 'lucide-react'

function StatCard({ label, value, sub, icon: Icon, accent = '#f59e0b', glow = false }) {
  return (
    <div className={`panel px-4 py-3 flex items-start gap-3 ${glow ? 'glow-amber' : ''}`}>
      <div className="mt-0.5 p-1.5 rounded" style={{ background: `${accent}18` }}>
        <Icon size={14} style={{ color: accent }} />
      </div>
      <div className="min-w-0">
        <div className="mono text-xl font-medium leading-none count-up" style={{ color: accent }}>
          {value ?? '—'}
        </div>
        <div className="text-xs mt-1" style={{ color: 'var(--text-2)' }}>{label}</div>
        {sub && <div className="text-xs mt-0.5" style={{ color: 'var(--text-3)' }}>{sub}</div>}
      </div>
    </div>
  )
}

export default function StatsBar() {
  const { data, loading } = useApiData('/dashboard/stats', {}, 30000)

  const s = data || {}

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
      <StatCard
        label="Total Articles"
        value={fmtNum(s.total_articles)}
        sub={`+${fmtNum(s.articles_24h)} today`}
        icon={Database}
        accent="#f59e0b"
        glow={true}
      />
      <StatCard
        label="Track A (Targeted)"
        value={fmtNum(s.track_a)}
        sub="keyword-matched"
        icon={Rss}
        accent="#4ade80"
      />
      <StatCard
        label="Track B (Hot News)"
        value={fmtNum(s.track_b)}
        sub={`${fmtNum(s.gemini_screened)} screened`}
        icon={Activity}
        accent="#60a5fa"
      />
      <StatCard
        label="Confirmed Risks"
        value={fmtNum(s.confirmed_risks)}
        sub={`${fmtNum(s.indirect_risks)} indirect`}
        icon={AlertTriangle}
        accent="#ef4444"
        glow={s.confirmed_risks > 0}
      />
      <StatCard
        label="Suppliers Tracked"
        value={fmtNum(s.active_suppliers)}
        sub={`${fmtNum(s.critical_suppliers)} critical`}
        icon={Shield}
        accent="#a78bfa"
      />
      <StatCard
        label="Last Ingestion"
        value={s.last_fetch ? timeAgo(s.last_fetch) : '—'}
        sub={s.last_fetch_status || 'never'}
        icon={Clock}
        accent={s.last_fetch_status === 'success' ? '#22c55e' : '#ef4444'}
      />
    </div>
  )
}
