// src/components/AlternatesPanel.jsx
import { useApiData } from '../hooks/useApi'
import { GitBranch, AlertTriangle, Clock, MapPin, TrendingUp } from 'lucide-react'

const BAND_COLOR = {
  CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308',
  LOW: '#3b82f6', WATCH: '#6b7280',
}

const CAP_COLOR = { high: '#22c55e', medium: '#f59e0b', low: '#6b7280' }
const CAP_LABEL = { high: 'High', medium: 'Medium', low: 'Low' }

function ScoreBar({ value, color = '#f59e0b' }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, height: 3, borderRadius: 2, background: 'var(--surface-3)', overflow: 'hidden' }}>
        <div style={{ width: `${value}%`, height: '100%', borderRadius: 2, background: color }} />
      </div>
      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--text-3)', flexShrink: 0, width: 22, textAlign: 'right' }}>
        {Math.round(value)}
      </span>
    </div>
  )
}

function AlternateCard({ alt, rank }) {
  const rankColor = rank === 1 ? '#f59e0b' : rank === 2 ? '#8b949e' : '#6b7280'
  const capColor = CAP_COLOR[alt.capacity_fit] || '#6b7280'

  return (
    <div style={{
      margin: '0 0 12px 0', padding: 14, borderRadius: 6,
      background: 'var(--surface-2)',
      border: rank === 1 ? '1px solid #f59e0b30' : '1px solid var(--surface-3)',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 }}>
        <div style={{
          width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: `${rankColor}22`, border: `1px solid ${rankColor}44`,
          fontFamily: 'DM Mono, monospace', fontSize: 10, color: rankColor, fontWeight: 600,
        }}>
          {rank}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', marginBottom: 2 }}>
            {alt.alternate_name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <MapPin size={9} style={{ color: 'var(--text-3)' }} />
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{alt.country}</span>
            <Clock size={9} style={{ color: 'var(--text-3)' }} />
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{alt.lead_time_weeks}w lead time</span>
          </div>
        </div>
        {/* Overall score */}
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 18, fontWeight: 700, color: rankColor, lineHeight: 1 }}>
            {Math.round(alt.alt_score)}
          </div>
          <div style={{ fontSize: 9, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            score
          </div>
        </div>
      </div>

      {/* Score breakdown */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 12px', marginBottom: 10 }}>
        {[
          { label: 'Capacity',    value: alt.capacity_fit ? (CAP_COLOR[alt.capacity_fit] ? { pct: {high:88,medium:55,low:25}[alt.capacity_fit], color: capColor } : null) : null },
          { label: 'Geo Safety',  value: alt.geographic_safety_score != null ? { pct: alt.geographic_safety_score, color: alt.geographic_safety_score > 70 ? '#22c55e' : alt.geographic_safety_score > 40 ? '#f59e0b' : '#ef4444' } : null },
          { label: 'Track Record',value: alt.track_record_score != null ? { pct: alt.track_record_score, color: '#60a5fa' } : null },
        ].filter(r => r.value).map(({ label, value }) => (
          <div key={label}>
            <div style={{ fontSize: 9, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>
              {label}
            </div>
            <ScoreBar value={value.pct} color={value.color} />
          </div>
        ))}
        {/* Capacity tag */}
        <div>
          <div style={{ fontSize: 9, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 3 }}>
            Capacity Fit
          </div>
          <span style={{
            fontFamily: 'DM Mono, monospace', fontSize: 9, textTransform: 'uppercase',
            letterSpacing: '0.04em', color: capColor,
            background: `${capColor}18`, border: `1px solid ${capColor}30`,
            padding: '1px 5px', borderRadius: 3,
          }}>
            {CAP_LABEL[alt.capacity_fit] || alt.capacity_fit}
          </span>
        </div>
      </div>

      {/* Rationale */}
      {alt.rationale && (
        <p style={{ fontSize: 11, lineHeight: 1.6, color: 'var(--text-2)', margin: 0, fontStyle: 'italic' }}>
          {alt.rationale}
        </p>
      )}
    </div>
  )
}

function RiskEventBlock({ item }) {
  const re = item.risk_event
  const dis = item.disrupted_supplier
  if (!re) return null

  const bandColor = BAND_COLOR[re.severity_band] || '#6b7280'

  // Group all alternates for this event
  return null  // handled in parent
}

export default function AlternatesPanel() {
  const { data, loading } = useApiData('/alternates/', { limit: 50 }, 60000)
  const items = data?.items || []
  const total = data?.total || 0

  // Group by risk_event_id
  const grouped = {}
  for (const item of items) {
    const eid = item.risk_event?.id ?? 'unknown'
    if (!grouped[eid]) grouped[eid] = { risk_event: item.risk_event, disrupted: item.disrupted_supplier, alts: [] }
    grouped[eid].alts.push(item)
  }
  const groups = Object.values(grouped)
  // Sort by risk score descending
  groups.sort((a, b) => (b.risk_event?.risk_score ?? 0) - (a.risk_event?.risk_score ?? 0))

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px', borderBottom: '1px solid var(--surface-3)', flexShrink: 0,
      }}>
        <GitBranch size={12} style={{ color: 'var(--amber)' }} />
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, fontWeight: 500, color: 'var(--amber)' }}>
          ALTERNATE SUPPLIERS
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-3)' }}>
          {total} recommendations
        </span>
      </div>

      <div style={{ overflowY: 'auto', flex: 1, padding: 16 }}>
        {loading && !items.length && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, fontSize: 13, color: 'var(--text-3)' }}>
            Loading…
          </div>
        )}

        {!loading && !items.length && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 120, gap: 8 }}>
            <span style={{ fontSize: 24 }}>🔍</span>
            <span style={{ fontSize: 13, color: 'var(--text-3)', textAlign: 'center' }}>
              No recommendations yet
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
              Run Module 3 after HIGH+ risk events are scored
            </span>
            <code style={{ fontSize: 10, color: 'var(--amber)', background: 'var(--surface-2)', padding: '3px 8px', borderRadius: 4 }}>
              python -m module3.main --run-once
            </code>
          </div>
        )}

        {groups.map(({ risk_event: re, disrupted: dis, alts }) => {
          if (!re) return null
          const bandColor = BAND_COLOR[re.severity_band] || '#6b7280'
          const sortedAlts = [...alts].sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99))

          return (
            <div key={re.id} style={{ marginBottom: 24 }}>
              {/* Risk event header */}
              <div style={{
                padding: '8px 12px', borderRadius: 5, marginBottom: 12,
                background: `${bandColor}12`, border: `1px solid ${bandColor}30`,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <AlertTriangle size={11} style={{ color: bandColor, flexShrink: 0 }} />
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: bandColor, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    {re.severity_band}
                  </span>
                  <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: bandColor, fontWeight: 600 }}>
                    {re.risk_score?.toFixed(0)}
                  </span>
                  {re.is_indirect && (
                    <span style={{
                      fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.05em',
                      color: '#a78bfa', background: '#a78bfa18', border: '1px solid #a78bfa30',
                      padding: '1px 5px', borderRadius: 3, fontFamily: 'DM Mono, monospace',
                    }}>
                      Indirect
                    </span>
                  )}
                </div>
                {dis && (
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-1)' }}>
                    {dis.name}
                    <span style={{ fontSize: 11, fontWeight: 400, color: 'var(--text-3)', marginLeft: 6 }}>
                      · {re.commodity?.split('(')[0].trim()}
                    </span>
                  </div>
                )}
                {re.event_type && (
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2, textTransform: 'capitalize' }}>
                    {re.event_type.replace('_', ' ')}
                  </div>
                )}
              </div>

              {/* Alternate cards */}
              {sortedAlts.map(alt => (
                <AlternateCard key={alt.id} alt={alt} rank={alt.rank ?? 1} />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
