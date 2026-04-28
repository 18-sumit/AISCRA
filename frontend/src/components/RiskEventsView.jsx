// src/components/RiskEventsView.jsx
import { useState } from 'react'
import { useApiData, apiFetch } from '../hooks/useApi'
import { timeAgo } from '../utils'
import { AlertTriangle, ChevronDown, ChevronRight, Settings, SlidersHorizontal } from 'lucide-react'

const BAND_COLOR = {
  CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308',
  LOW: '#3b82f6', WATCH: '#6b7280',
}

// ─────────────────────────────────────────────────────────────────────────────
//  Score breakdown bar
// ─────────────────────────────────────────────────────────────────────────────
function ScoreComponent({ label, value, weight, color = '#f59e0b' }) {
  const contribution = (value * weight).toFixed(1)
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{label}</span>
        <div style={{ display: 'flex', gap: 10 }}>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-3)' }}>
            ×{weight} =
          </span>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color, minWidth: 28, textAlign: 'right' }}>
            {contribution}
          </span>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--surface-3)', overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(value, 100)}%`, height: '100%', background: color, borderRadius: 2, opacity: 0.85 }} />
        </div>
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--text-3)', width: 28, textAlign: 'right' }}>
          {value?.toFixed(0) ?? '—'}
        </span>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  Single risk event row
// ─────────────────────────────────────────────────────────────────────────────
function RiskEventRow({ event, thresholds }) {
  const [expanded, setExpanded] = useState(false)
  const band = event.severity_band || 'WATCH'
  const color = BAND_COLOR[band] || '#6b7280'
  const score = event.risk_score || 0

  return (
    <div style={{ borderBottom: '1px solid var(--surface-3)' }}>
      {/* Summary row */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '12px 16px', cursor: 'pointer',
          transition: 'background 0.15s',
        }}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-2)'}
        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
      >
        {/* Score badge */}
        <div style={{
          width: 44, height: 44, borderRadius: 6, flexShrink: 0,
          display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
          background: `${color}18`, border: `1px solid ${color}40`,
        }}>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 14, fontWeight: 700, color, lineHeight: 1 }}>
            {score.toFixed(0)}
          </span>
          <span style={{ fontSize: 8, color, textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: 1 }}>
            {band}
          </span>
        </div>

        {/* Event info */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {event.supplier?.name || 'Unknown Supplier'}
            </span>
            {event.is_indirect && (
              <span style={{
                fontSize: 9, fontFamily: 'DM Mono, monospace', textTransform: 'uppercase',
                letterSpacing: '0.05em', color: '#a78bfa',
                background: '#a78bfa18', border: '1px solid #a78bfa30',
                padding: '1px 5px', borderRadius: 3, flexShrink: 0,
              }}>Indirect</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
              {event.commodity?.split('(')[0].trim()}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>·</span>
            <span style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'capitalize' }}>
              {event.event_type?.replace('_', ' ')}
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>·</span>
            <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
              {timeAgo(event.created_at)}
            </span>
          </div>
        </div>

        {/* Expand toggle */}
        <div style={{ color: 'var(--text-3)', flexShrink: 0 }}>
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ padding: '0 16px 16px 72px' }}>

          {/* Score breakdown */}
          <div style={{
            padding: 12, borderRadius: 5, background: 'var(--surface-2)',
            marginBottom: 12,
          }}>
            <div style={{
              fontSize: 10, fontFamily: 'DM Mono, monospace', textTransform: 'uppercase',
              letterSpacing: '0.06em', color: 'var(--text-3)', marginBottom: 12,
            }}>
              Score Breakdown — total: {score.toFixed(1)}
              {event.is_indirect && event.article?.gemini_confidence && (
                <span style={{ color: '#a78bfa', marginLeft: 8 }}>
                  (raw × {(event.article.gemini_confidence * 100).toFixed(0)}% confidence = {score.toFixed(1)})
                </span>
              )}
            </div>

            {/* We reconstruct approximate components from what the API gives us */}
            <ScoreComponent label="Event Severity"         value={event.severity_score ?? 45}       weight={0.35} color="#ef4444" />
            <ScoreComponent label="Dependency Criticality" value={event.dep_score ?? 50}             weight={0.30} color="#f97316" />
            <ScoreComponent label="Geographic Risk"        value={event.geo_score ?? 40}             weight={0.15} color="#eab308" />
            <ScoreComponent label="Recency"                value={event.recency_score ?? 60}          weight={0.12} color="#22c55e" />
            <ScoreComponent label="Source Credibility"     value={event.credibility_score ?? 30}     weight={0.08} color="#60a5fa" />
          </div>

          {/* Supplier details */}
          {event.supplier && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '8px 16px', marginBottom: 12 }}>
              {[
                ['Country',      event.supplier.country],
                ['Tier',         `Tier ${event.supplier.tier}`],
                ['Criticality',  event.supplier.criticality],
                ['Dependency',   `${((event.supplier.dependency_weight || 0) * 100).toFixed(0)}%`],
              ].map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 9, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{k}</div>
                  <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-2)', marginTop: 2, textTransform: 'capitalize' }}>{v}</div>
                </div>
              ))}
            </div>
          )}

          {/* Propagation pathway */}
          {event.impact_chain && (
            <div style={{ fontSize: 11, lineHeight: 1.7, color: 'var(--text-2)', fontStyle: 'italic' }}>
              {event.impact_chain}
            </div>
          )}

          {/* Article headline */}
          {event.article?.headline && (
            <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-3)' }}>
              Source: {event.article.headline}
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
//  Threshold settings panel
// ─────────────────────────────────────────────────────────────────────────────
function ThresholdSettings({ thresholds, onSave }) {
  const [local, setLocal] = useState({ ...thresholds })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const BAND_DEF = [
    { key: 'critical', label: 'CRITICAL threshold', color: '#ef4444', min: 60, max: 100 },
    { key: 'high',     label: 'HIGH threshold',     color: '#f97316', min: 40, max: 90  },
    { key: 'medium',   label: 'MEDIUM threshold',   color: '#eab308', min: 20, max: 70  },
    { key: 'low',      label: 'LOW threshold',      color: '#3b82f6', min: 0,  max: 50  },
  ]

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetch('/api/dashboard/thresholds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(local),
      })
      onSave(local)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      console.error(e)
    }
    setSaving(false)
  }

  return (
    <div className="panel" style={{ padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <SlidersHorizontal size={12} style={{ color: 'var(--amber)' }} />
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--amber)', letterSpacing: '0.06em' }}>
          RISK THRESHOLDS
        </span>
      </div>

      <p style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 16, lineHeight: 1.5 }}>
        Adjust score thresholds for each severity band. Lowering the HIGH threshold triggers alternate recommendations at lower scores — useful for demonstration or conservative risk management.
      </p>

      {BAND_DEF.map(({ key, label, color, min, max }) => (
        <div key={key} style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--text-2)' }}>{label}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 12, fontWeight: 600, color }}>
              ≥ {local[key]}
            </span>
          </div>
          <input
            type="range" min={min} max={max} step={5}
            value={local[key]}
            onChange={e => setLocal(l => ({ ...l, [key]: Number(e.target.value) }))}
            style={{ width: '100%', accentColor: color, height: 3, cursor: 'pointer' }}
          />
        </div>
      ))}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            fontFamily: 'DM Mono, monospace', fontSize: 11, padding: '5px 14px',
            borderRadius: 4, border: '1px solid var(--amber)', cursor: 'pointer',
            background: saved ? '#22c55e22' : 'transparent',
            color: saved ? '#22c55e' : 'var(--amber)',
            transition: 'all 0.2s',
          }}
        >
          {saved ? '✓ Saved' : saving ? 'Saving…' : 'Apply'}
        </button>
      </div>
    </div>
  )
}


// ─────────────────────────────────────────────────────────────────────────────
//  Main view
// ─────────────────────────────────────────────────────────────────────────────
export default function RiskEventsView() {
  const [severityFilter, setSeverityFilter] = useState('all')

  const { data: eventsData, loading: eventsLoading } = useApiData('/risk-events/', { limit: 100 }, 30000)
  const { data: thresholds, reload: reloadThresholds }   = useApiData('/dashboard/thresholds', {}, 0)

  const events = eventsData?.items || []
  const total  = eventsData?.total  || 0

  const filtered = severityFilter === 'all'
    ? events
    : events.filter(e => e.severity_band === severityFilter)

  const FILTERS = [
    { id: 'all',      label: `All (${total})` },
    { id: 'CRITICAL', label: `Critical (${events.filter(e => e.severity_band === 'CRITICAL').length})` },
    { id: 'HIGH',     label: `High (${events.filter(e => e.severity_band === 'HIGH').length})` },
    { id: 'MEDIUM',   label: `Medium (${events.filter(e => e.severity_band === 'MEDIUM').length})` },
    { id: 'LOW',      label: `Low (${events.filter(e => e.severity_band === 'LOW').length})` },
  ]

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: 16, height: '100%', minHeight: 0 }}>

      {/* Left — events list */}
      <div className="panel" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 16px', borderBottom: '1px solid var(--surface-3)', flexShrink: 0,
        }}>
          <AlertTriangle size={12} style={{ color: 'var(--amber)' }} />
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, fontWeight: 500, color: 'var(--amber)' }}>
            RISK EVENTS
          </span>

          {/* Band filters */}
          <div style={{ display: 'flex', gap: 2, marginLeft: 8 }}>
            {FILTERS.map(f => (
              <button key={f.id} onClick={() => setSeverityFilter(f.id)}
                style={{
                  padding: '3px 8px', fontSize: 10, borderRadius: 4, border: 'none',
                  fontFamily: 'DM Mono, monospace', cursor: 'pointer',
                  background: severityFilter === f.id ? 'var(--surface-3)' : 'transparent',
                  color: severityFilter === f.id
                    ? (BAND_COLOR[f.id] || 'var(--amber)')
                    : 'var(--text-3)',
                }}
              >{f.label}</button>
            ))}
          </div>
        </div>

        {/* Event list */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {eventsLoading && !events.length && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, fontSize: 13, color: 'var(--text-3)' }}>
              Loading…
            </div>
          )}
          {!eventsLoading && !filtered.length && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 120, gap: 8 }}>
              <span style={{ fontSize: 22 }}>📊</span>
              <span style={{ fontSize: 13, color: 'var(--text-3)' }}>
                {total === 0 ? 'No risk events yet — run Module 2' : `No ${severityFilter} events`}
              </span>
              {total === 0 && (
                <code style={{ fontSize: 10, color: 'var(--amber)', background: 'var(--surface-2)', padding: '3px 8px', borderRadius: 4 }}>
                  python -m module2.main --run-once
                </code>
              )}
            </div>
          )}
          {filtered.map(e => (
            <RiskEventRow key={e.id} event={e} thresholds={thresholds || {}} />
          ))}
        </div>
      </div>

      {/* Right — always show settings / explanation */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, overflowY: 'auto' }}>
        {thresholds && (
          <ThresholdSettings
            thresholds={thresholds}
            onSave={() => reloadThresholds()}
          />
        )}

        {/* Formula explanation card */}
        <div className="panel" style={{ padding: 16 }}>
          <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--amber)', marginBottom: 12, letterSpacing: '0.06em' }}>
            SCORING FORMULA
          </div>
          {[
            { label: 'Event Severity',         weight: '35%', color: '#ef4444', desc: 'Rule-based event type + sentiment model' },
            { label: 'Dependency Criticality', weight: '30%', color: '#f97316', desc: 'Supplier tier, criticality & dependency weight' },
            { label: 'Geographic Risk',        weight: '15%', color: '#eab308', desc: 'Country risk index (0–100)' },
            { label: 'Recency',                weight: '12%', color: '#22c55e', desc: 'Exponential decay from publish time' },
            { label: 'Source Credibility',     weight: '8%',  color: '#60a5fa', desc: 'Pre-seeded domain trust score' },
          ].map(({ label, weight, color, desc }) => (
            <div key={label} style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                <span style={{ fontSize: 11, color: 'var(--text-1)' }}>{label}</span>
                <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, fontWeight: 700, color }}>{weight}</span>
              </div>
              <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{desc}</span>
            </div>
          ))}
          <div style={{
            marginTop: 12, padding: '8px 10px', borderRadius: 4,
            background: 'var(--surface-2)', fontSize: 10,
            fontFamily: 'DM Mono, monospace', color: 'var(--text-3)', lineHeight: 1.7,
          }}>
            Indirect risks multiplied by<br />AI impact confidence score
          </div>
        </div>
      </div>
    </div>
  )
}
