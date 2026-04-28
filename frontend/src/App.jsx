// src/App.jsx
import { useState } from 'react'
import { useApiData } from './hooks/useApi'
import { timeAgo }    from './utils'
import StatsBar         from './components/StatsBar'
import ArticleFeed      from './components/ArticleFeed'
import SupplierPanel    from './components/SupplierPanel'
import CountryRiskTable from './components/CountryRiskTable'
import FetchLogsPanel   from './components/FetchLogsPanel'
import IngestionChart   from './components/IngestionChart'
import SourceBreakdown  from './components/SourceBreakdown'
import AlternatesPanel  from './components/AlternatesPanel'
import RiskEventsView   from './components/RiskEventsView'
import ChatPanel        from './components/ChatPanel'
import {
  Activity, Shield,
  Globe, RefreshCw, BarChart2,
  AlertTriangle, GitBranch, Zap, Sparkles,
} from 'lucide-react'

const S = {
  s0: '#080c10', s1: '#0d1117', s2: '#161b22',
  s3: '#21262d', s4: '#30363d',
  amber: '#f59e0b', text1: '#e6edf3',
  text2: '#8b949e', text3: '#484f58',
}

const NAV = [
  { id: 'feed',        label: 'Live Feed',     icon: Activity   },
  { id: 'risk-events', label: 'Risk Events',   icon: Zap        },
  { id: 'alternates',  label: 'Alternates',    icon: GitBranch  },
  { id: 'suppliers',   label: 'Suppliers',     icon: Shield     },
  { id: 'countries',   label: 'Country Risk',  icon: Globe      },
  { id: 'analytics',   label: 'Analytics',     icon: BarChart2  },
  { id: 'chat',        label: 'AI Chat',       icon: Sparkles   },
  { id: 'logs',        label: 'Ingest Logs',   icon: RefreshCw  },
]

function NavItem({ item, active, onClick }) {
  const isActive = active === item.id
  return (
    <button
      onClick={() => onClick(item.id)}
      style={{
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 16px',
        fontSize: '13px',
        fontFamily: 'IBM Plex Sans, sans-serif',
        background: isActive ? S.s3 : 'transparent',
        color:      isActive ? S.text1 : S.text3,
        border: 'none',
        borderLeft: isActive ? `2px solid ${S.amber}` : '2px solid transparent',
        cursor: 'pointer',
        transition: 'all 0.15s',
        textAlign: 'left',
      }}
    >
      <item.icon size={14} style={{ opacity: isActive ? 1 : 0.5, flexShrink: 0 }} />
      {item.label}
    </button>
  )
}

function Sidebar({ active, onChange, stats }) {
  return (
    <aside style={{
      width: 200,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      background: S.s1,
      borderRight: `1px solid ${S.s3}`,
    }}>
      {/* Logo */}
      <div style={{ padding: '20px 16px 16px', borderBottom: `1px solid ${S.s3}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <div style={{
            width: 24, height: 24, borderRadius: 4,
            background: '#f59e0b22', border: '1px solid #f59e0b44',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <AlertTriangle size={12} color={S.amber} />
          </div>
          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, fontWeight: 500, color: S.text1 }}>
            SC Risk
          </span>
        </div>
        <p style={{ fontSize: 11, color: S.text3, margin: 0 }}>Supply Chain Monitor</p>
      </div>

      {/* Company */}
      <div style={{ padding: '12px 16px', borderBottom: `1px solid ${S.s3}` }}>
        <div style={{ fontSize: 11, color: S.text3 }}>Monitoring</div>
        <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 13, color: S.amber, marginTop: 2, fontWeight: 500 }}>
          Cipla Limited
        </div>
        <div style={{ fontSize: 11, color: S.text3, marginTop: 2 }}>
          {stats?.active_suppliers ?? '—'} suppliers tracked
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, paddingTop: 8 }}>
        {NAV.map(item => (
          <NavItem key={item.id} item={item} active={active} onClick={onChange} />
        ))}
      </nav>

      {/* Footer */}
      <div style={{ padding: '12px 16px', borderTop: `1px solid ${S.s3}` }}>
        {[
          { label: 'Total articles', value: stats?.total_articles?.toLocaleString() },
          { label: 'Last fetch',     value: stats?.last_fetch ? timeAgo(stats.last_fetch) : '—' },
          { label: 'Status',         value: stats?.last_fetch_status ?? '—',
            color: stats?.last_fetch_status === 'success' ? '#22c55e' : '#6b7280' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: S.text3 }}>{label}</span>
            <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: color || S.text2 }}>
              {value}
            </span>
          </div>
        ))}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
          <span className="pulse-dot live" />
          <span style={{ fontSize: 11, color: S.text3 }}>auto-refresh on</span>
        </div>
      </div>
    </aside>
  )
}

function TopBar({ view, stats }) {
  const current = NAV.find(n => n.id === view)
  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '0 20px',
      height: 44,
      background: S.s1,
      borderBottom: `1px solid ${S.s3}`,
      flexShrink: 0,
    }}>
      <current.icon size={13} color={S.amber} />
      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: S.amber, letterSpacing: '0.06em' }}>
        {current?.label?.toUpperCase()}
      </span>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
        {stats?.confirmed_risks > 0 && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '3px 10px', borderRadius: 4, fontSize: 11,
            fontFamily: 'DM Mono, monospace',
            background: '#200f0f', color: '#f87171',
            border: '1px solid #3d1515',
          }}>
            <AlertTriangle size={10} />
            {stats.confirmed_risks} risk{stats.confirmed_risks > 1 ? 's' : ''} detected
          </div>
        )}
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: S.text3 }}>
          {new Date().toLocaleTimeString('en-US', { hour12: false })}
        </span>
      </div>
    </header>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
//  Analytics view — live module status from API
// ─────────────────────────────────────────────────────────────────────────────

function ModuleStatusPanel() {
  const { data, loading } = useApiData('/dashboard/module-status', {}, 30000)

  const STATUS_COLOR = { active: '#22c55e', partial: '#f59e0b', pending: '#6b7280' }

  const modules = [
    {
      key: 'module1', label: 'Module 1 — Data Ingestion',
      detail: d => d ? `${(d.runs || 0).toLocaleString()} ingestion runs` : '',
    },
    {
      key: 'module2', label: 'Module 2 — Risk Analysis',
      detail: d => d ? `${(d.risk_events || 0).toLocaleString()} risk events · ${d.high_plus || 0} HIGH+` : '',
    },
    {
      key: 'module3', label: 'Module 3 — Alternate Recommender',
      detail: d => d
        ? d.alternates > 0
          ? `${d.alternates} recommendations · ${d.events_covered} events covered`
          : d.pending_events > 0
            ? `${d.pending_events} HIGH+ events awaiting recommendations`
            : 'No HIGH+ risk events yet'
        : '',
    },
    {
      key: 'module4', label: 'Module 4 — AI Agent',
      detail: () => 'Dashboard live · conversational agent pending',
    },
  ]

  return (
    <div className="panel" style={{ padding: 16 }}>
      <div style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--amber)', marginBottom: 14, letterSpacing: '0.06em' }}>
        MODULE STATUS
      </div>
      {modules.map(({ key, label, detail }) => {
        const moduleData = data?.[key]
        const status = moduleData?.status || 'pending'
        const color  = STATUS_COLOR[status] || '#6b7280'
        const detailText = detail(moduleData)
        return (
          <div key={key} style={{
            display: 'flex', alignItems: 'flex-start', gap: 10,
            padding: '10px 0', borderBottom: '1px solid var(--surface-3)',
          }}>
            <div style={{
              width: 7, height: 7, borderRadius: '50%',
              background: status === 'active' ? color : 'transparent',
              border: `2px solid ${color}`,
              flexShrink: 0, marginTop: 3,
              boxShadow: status === 'active' ? `0 0 6px ${color}66` : 'none',
            }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: 'var(--text-1)' }}>{label}</div>
              {detailText && (
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{detailText}</div>
              )}
            </div>
            <span style={{
              fontFamily: 'DM Mono, monospace', fontSize: 10,
              textTransform: 'uppercase', letterSpacing: '0.05em',
              color, flexShrink: 0,
            }}>
              {loading ? '…' : status}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function AnalyticsView() {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
      <div style={{ gridColumn: '1 / -1' }}>
        <IngestionChart />
      </div>
      <SourceBreakdown />
      <ModuleStatusPanel />
    </div>
  )
}

export default function App() {
  const [view, setView] = useState('feed')
  const { data: stats } = useApiData('/dashboard/stats', {}, 30000)

  return (
    <div className="grid-bg" style={{
      display: 'flex',
      height: '100vh',
      overflow: 'hidden',
    }}>
      <Sidebar active={view} onChange={setView} stats={stats} />

      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        <TopBar view={view} stats={stats} />

        <div style={{ flex: 1, overflow: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <StatsBar />

          {view === 'feed' && (
            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, flex: 1, minHeight: 0 }}>
              <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <ArticleFeed />
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <SupplierPanel />
              </div>
            </div>
          )}

          {view === 'risk-events' && (
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <RiskEventsView />
            </div>
          )}

          {view === 'alternates' && (
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <AlternatesPanel />
            </div>
          )}

          {view === 'suppliers' && (
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <SupplierPanel />
            </div>
          )}

          {view === 'countries' && (
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <CountryRiskTable />
            </div>
          )}

          {view === 'analytics' && (
            <AnalyticsView />
          )}

          {view === 'chat' && (
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <ChatPanel />
            </div>
          )}

          {view === 'logs' && (
            <div style={{ flex: 1, overflow: 'hidden' }}>
              <FetchLogsPanel />
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

