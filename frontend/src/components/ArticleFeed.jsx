// src/components/ArticleFeed.jsx
import { useState } from 'react'
import { useApiData } from '../hooks/useApi'
import { timeAgo } from '../utils'
import { Search, ExternalLink, ChevronRight, AlertTriangle, Globe, Target, SlidersHorizontal } from 'lucide-react'

const BAND_COLOR = {
  CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308',
  LOW: '#3b82f6', WATCH: '#6b7280',
}

function RiskBadge({ article }) {
  if (article.is_supply_chain_risk === true)
    return <span className="tag tag-critical"><AlertTriangle size={8} /> Risk Detected</span>
  if (article.is_indirect_risk)
    return <span className="tag tag-risk">Indirect Exposure</span>
  if (article.is_relevant_prefilter)
    return <span className="tag tag-high">Relevant Signal</span>
  return null
}

function TrackBadge({ fetch_type }) {
  return fetch_type === 'targeted'
    ? <span className="tag tag-a"><Target size={8} /> Track A</span>
    : <span className="tag tag-b"><Globe size={8} /> Track B</span>
}

function ConfidenceBar({ value }) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const color = value > 0.75 ? '#ef4444' : value > 0.5 ? '#f59e0b' : '#6b7280'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 11, color: 'var(--text-3)', flexShrink: 0 }}>Impact confidence</span>
      <div style={{ flex: 1, height: 4, borderRadius: 2, background: 'var(--surface-3)', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-2)', flexShrink: 0 }}>
        {pct}%
      </span>
    </div>
  )
}

function ArticleRow({ article, onClick, selected }) {
  return (
    <div
      onClick={() => onClick(article)}
      className="animate-slide-up"
      style={{
        padding: '12px 16px', borderBottom: '1px solid var(--surface-3)',
        cursor: 'pointer', background: selected ? 'var(--surface-2)' : 'transparent',
        transition: 'background 0.15s',
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = '#161b2260' }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent' }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4 }}>
        <TrackBadge fetch_type={article.fetch_type} />
        <RiskBadge article={article} />
        <span style={{ marginLeft: 'auto', fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--text-3)', flexShrink: 0 }}>
          {timeAgo(article.fetched_at)}
        </span>
      </div>
      <p style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.4, marginBottom: 4, color: 'var(--text-1)' }}>
        {article.headline}
      </p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
          {article.source_name || article.source_domain || 'Unknown'}
        </span>
        {article.affected_commodities?.length > 0 && (
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
            · {article.affected_commodities.slice(0, 2).join(', ')}
          </span>
        )}
      </div>
    </div>
  )
}

function ArticleDetail({ article, onClose }) {
  if (!article) return null
  const horizonLabel = {
    immediate: 'Immediate (days)',
    weeks: 'Short-term (2–8 weeks)',
    months: 'Medium-term (1–6 months)',
  }
  const plausibilityColor = { high: '#ef4444', medium: '#f59e0b', low: '#6b7280' }

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px', borderBottom: '1px solid var(--surface-3)', flexShrink: 0,
      }}>
        <TrackBadge fetch_type={article.fetch_type} />
        {article.is_supply_chain_risk && <span className="tag tag-critical">Risk Detected</span>}
        {article.gemini_plausibility && (
          <span style={{
            fontFamily: 'DM Mono, monospace', fontSize: 10, textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: plausibilityColor[article.gemini_plausibility] || '#6b7280',
          }}>
            {article.gemini_plausibility} plausibility
          </span>
        )}
        <button onClick={onClose} style={{
          marginLeft: 'auto', fontSize: 11, padding: '2px 8px', borderRadius: 4,
          border: 'none', cursor: 'pointer', background: 'transparent', color: 'var(--text-3)',
        }}>✕ close</button>
      </div>

      <div style={{ overflowY: 'auto', flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {/* Headline */}
        <div>
          <h2 style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4, marginBottom: 6, color: 'var(--text-1)' }}>
            {article.headline}
          </h2>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 11, color: 'var(--text-2)' }}>
              {article.source_name} · {timeAgo(article.published_at)}
            </span>
            <a href={article.url} target="_blank" rel="noopener noreferrer"
              style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--amber)', textDecoration: 'none' }}>
              <ExternalLink size={10} /> Read source
            </a>
          </div>
        </div>

        {/* Propagation Pathway */}
        {article.impact_chain && (
          <div style={{ borderRadius: 4, padding: 12, background: 'var(--surface-2)' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8,
              fontSize: 10, fontWeight: 600, textTransform: 'uppercase',
              letterSpacing: '0.06em', color: '#a78bfa',
            }}>
              <ChevronRight size={12} /> Propagation Pathway
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--text-2)', margin: 0 }}>
              {article.impact_chain}
            </p>
          </div>
        )}

        {/* Impact confidence */}
        <ConfidenceBar value={article.gemini_confidence} />

        {/* Exposed suppliers */}
        {article.affected_suppliers?.length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              Exposed Suppliers
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {article.affected_suppliers.map(s => <span key={s} className="tag tag-critical">{s}</span>)}
            </div>
          </div>
        )}

        {/* At-risk commodities */}
        {article.affected_commodities?.length > 0 && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              At-Risk Commodities
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {article.affected_commodities.map(c => <span key={c} className="tag tag-medium">{c}</span>)}
            </div>
          </div>
        )}

        {/* Abstract */}
        {article.summary && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
              Abstract
            </div>
            <p style={{ fontSize: 12, lineHeight: 1.6, color: 'var(--text-2)', margin: 0 }}>{article.summary}</p>
          </div>
        )}

        {/* Metadata */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px 16px',
          paddingTop: 12, borderTop: '1px solid var(--surface-3)',
        }}>
          {[
            ['Source Domain',   article.source_domain],
            ['Ingested',        timeAgo(article.fetched_at)],
            ['Published',       timeAgo(article.published_at)],
            ['Time to Impact',  horizonLabel[article.time_horizon] || article.time_horizon],
            ['Exposure Type',   article.is_indirect_risk ? 'Indirect (cascading)' : 'Direct'],
            ['Analysis Status', article.processed ? 'Scored by M2' : 'Awaiting analysis'],
          ].map(([k, v]) => v ? (
            <div key={k}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{k}</div>
              <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-2)', marginTop: 2 }}>{v}</div>
            </div>
          ) : null)}
        </div>
      </div>
    </div>
  )
}

function RiskSlider({ min, onChange }) {
  const band = min >= 80 ? 'CRITICAL' : min >= 60 ? 'HIGH' : min >= 40 ? 'MEDIUM' : min >= 20 ? 'LOW' : 'ALL'
  const color = BAND_COLOR[band] || '#f59e0b'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 16px', borderBottom: '1px solid var(--surface-3)',
      background: 'var(--surface-2)', flexShrink: 0,
    }}>
      <SlidersHorizontal size={11} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--text-3)', flexShrink: 0 }}>
        MIN SCORE
      </span>
      <input
        type="range" min={0} max={90} step={10} value={min}
        onChange={e => onChange(Number(e.target.value))}
        style={{ flex: 1, height: 3, cursor: 'pointer', accentColor: color }}
      />
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, fontWeight: 600, color, minWidth: 28, textAlign: 'right' }}>
          {min > 0 ? min : '—'}
        </span>
        {band !== 'ALL' && (
          <span style={{
            fontFamily: 'DM Mono, monospace', fontSize: 9, textTransform: 'uppercase',
            letterSpacing: '0.06em', color, background: `${color}18`,
            border: `1px solid ${color}40`, padding: '1px 5px', borderRadius: 3,
          }}>
            {band}+
          </span>
        )}
      </div>
    </div>
  )
}

export default function ArticleFeed() {
  const [tab,      setTab]      = useState('all')
  const [search,   setSearch]   = useState('')
  const [selected, setSelected] = useState(null)
  const [page,     setPage]     = useState(1)
  const [minScore, setMinScore] = useState(0)

  const params = {
    fetch_type: tab === 'all' ? undefined : tab === 'a' ? 'targeted' : 'hot_news',
    risk_only:  tab === 'risk' ? true : undefined,
    search:     search || undefined,
    page, page_size: 40, hours: 72,
  }

  const { data, loading } = useApiData('/articles/', params, 60000)
  let items = data?.items || []
  const total = data?.total || 0

  // Client-side confidence threshold filter on risk tab
  if (tab === 'risk' && minScore > 0) {
    const threshold = minScore / 100
    items = items.filter(a =>
      (a.gemini_confidence != null && a.gemini_confidence >= threshold) ||
      (a.is_supply_chain_risk && minScore <= 40)
    )
  }

  const TABS = [
    { id: 'all',  label: 'All Feeds' },
    { id: 'a',    label: 'Track A'   },
    { id: 'b',    label: 'Track B'   },
    { id: 'risk', label: '⚠ Risks'  },
  ]

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, height: '100%' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '8px 16px', borderBottom: '1px solid var(--surface-3)', flexShrink: 0,
      }}>
        <span className="pulse-dot live" style={{ marginRight: 2 }} />
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, fontWeight: 500, color: 'var(--amber)' }}>
          LIVE FEED
        </span>
        <div style={{ display: 'flex', gap: 2, marginLeft: 12 }}>
          {TABS.map(t => (
            <button key={t.id}
              onClick={() => { setTab(t.id); setPage(1); setMinScore(0) }}
              style={{
                padding: '3px 10px', fontSize: 11, borderRadius: 4,
                fontFamily: 'DM Mono, monospace', border: 'none', cursor: 'pointer',
                background: tab === t.id ? 'var(--surface-3)' : 'transparent',
                color:      tab === t.id ? 'var(--amber)'     : 'var(--text-3)',
              }}
            >{t.label}</button>
          ))}
        </div>
        <div style={{
          marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6,
          borderRadius: 4, padding: '4px 8px', background: 'var(--surface-2)',
        }}>
          <Search size={11} style={{ color: 'var(--text-3)' }} />
          <input value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="search headlines…"
            style={{ background: 'transparent', border: 'none', outline: 'none', fontSize: 11, width: 150, color: 'var(--text-1)', fontFamily: 'DM Mono, monospace' }}
          />
        </div>
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-3)' }}>
          {total.toLocaleString()} articles
        </span>
      </div>

      {/* Risk score slider — only on risk tab */}
      {tab === 'risk' && <RiskSlider min={minScore} onChange={v => { setMinScore(v); setPage(1) }} />}

      {/* Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: 0 }}>
        <div style={{ display: 'flex', flexDirection: 'column', overflowY: 'auto', width: selected ? '50%' : '100%', minHeight: 0 }}>
          {loading && !items.length && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, fontSize: 13, color: 'var(--text-3)' }}>
              Loading…
            </div>
          )}
          {!loading && !items.length && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 120, gap: 8 }}>
              <span style={{ fontSize: 24 }}>📭</span>
              <span style={{ fontSize: 13, color: 'var(--text-3)' }}>
                {tab === 'risk' ? 'No risk signals detected yet — run Module 2' : 'No articles yet — run --once to ingest'}
              </span>
            </div>
          )}
          {items.map(a => (
            <ArticleRow key={a.id} article={a} selected={selected?.id === a.id} onClick={setSelected} />
          ))}
          {total > 40 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, padding: '10px 0', flexShrink: 0 }}>
              <button disabled={page === 1} onClick={() => setPage(p => p - 1)}
                style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, padding: '4px 10px', borderRadius: 4, border: 'none', cursor: 'pointer', background: 'transparent', color: 'var(--text-2)', opacity: page === 1 ? 0.3 : 1 }}>
                ← prev
              </button>
              <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-3)' }}>
                {page} / {data?.pages}
              </span>
              <button disabled={page === data?.pages} onClick={() => setPage(p => p + 1)}
                style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, padding: '4px 10px', borderRadius: 4, border: 'none', cursor: 'pointer', background: 'transparent', color: 'var(--text-2)', opacity: page === data?.pages ? 0.3 : 1 }}>
                next →
              </button>
            </div>
          )}
        </div>

        {selected && (
          <div style={{ width: '50%', borderLeft: '1px solid var(--surface-3)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <ArticleDetail article={selected} onClose={() => setSelected(null)} />
          </div>
        )}
      </div>
    </div>
  )
}
