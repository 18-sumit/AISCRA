// src/components/FetchLogsPanel.jsx
import { useApiData } from '../hooks/useApi'
import { timeAgo } from '../utils'
import { RefreshCw } from 'lucide-react'

const STATUS_STYLE = {
  success: { color: '#22c55e', bg: '#16231620' },
  partial: { color: '#eab308', bg: '#2d290020' },
  failed:  { color: '#ef4444', bg: '#2d1a1a20' },
  skipped: { color: '#6b7280', bg: '#1c1c1c20' },
}

const SOURCE_LABELS = {
  track_a_combined: 'Track A — All Sources',
  track_b_combined: 'Track B — All Sources',
  newsapi_track_a:  'NewsAPI Track A',
  newsapi_track_b:  'NewsAPI Track B',
  gnews_track_a:    'GNews Track A',
  gnews_track_b:    'GNews Track B',
  rss_track_a:      'RSS Track A',
  rss_track_b:      'RSS Track B',
  gdelt_track_a:    'GDELT Track A',
  gdelt_track_b:    'GDELT Track B',
}

export default function FetchLogsPanel() {
  const { data: _logsdata, loading, reload } = useApiData('/logs/', { limit: 30 }, 60000)
  const logs = _logsdata || []

  return (
    <div className="panel flex flex-col h-full overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b shrink-0" style={{ borderColor: 'var(--surface-3)' }}>
        <RefreshCw size={12} style={{ color: 'var(--amber)' }} />
        <span className="mono text-xs font-medium" style={{ color: 'var(--amber)' }}>
          INGESTION HISTORY
        </span>
        <button
          onClick={reload}
          className="ml-auto p-1 rounded hover:bg-surface-3 transition-colors"
          title="Refresh"
        >
          <RefreshCw size={11} style={{ color: 'var(--text-3)' }} />
        </button>
      </div>

      <div className="overflow-y-auto flex-1">
        {loading && !logs.length && (
          <div className="flex items-center justify-center h-20 text-sm" style={{ color: 'var(--text-3)' }}>
            Loading…
          </div>
        )}
        {!loading && !logs.length && (
          <div className="flex items-center justify-center h-20 text-sm" style={{ color: 'var(--text-3)' }}>
            No runs yet — run --once to start
          </div>
        )}

        {logs.map(log => {
          const st = STATUS_STYLE[log.status] || STATUS_STYLE.skipped
          const label = SOURCE_LABELS[log.source] || log.source
          const track = log.fetch_type === 'targeted' ? 'A' : log.fetch_type === 'hot_news' ? 'B' : '?'

          return (
            <div
              key={log.id}
              className="px-4 py-3 border-b"
              style={{ borderColor: 'var(--surface-3)' }}
            >
              <div className="flex items-center gap-2 mb-1">
                {/* Status pill */}
                <span
                  className="tag"
                  style={{ background: st.bg, color: st.color, border: `1px solid ${st.color}30` }}
                >
                  {log.status}
                </span>

                {/* Track badge */}
                <span className={`tag tag-${track === 'A' ? 'a' : 'b'}`}>
                  Track {track}
                </span>

                <span className="mono text-xs ml-auto shrink-0" style={{ color: 'var(--text-3)' }}>
                  {timeAgo(log.run_at)}
                </span>
              </div>

              <p className="text-xs mb-1.5" style={{ color: 'var(--text-2)' }}>
                {label}
              </p>

              {/* Stats row */}
              <div className="flex gap-4">
                {[
                  { label: 'fetched', value: log.articles_fetched },
                  { label: 'new',     value: log.articles_new, accent: '#22c55e' },
                  { label: 'relevant',value: log.articles_relevant, accent: '#f59e0b' },
                  { label: 'time',    value: log.duration_seconds != null ? `${log.duration_seconds.toFixed(1)}s` : '—' },
                ].map(({ label, value, accent }) => (
                  <div key={label}>
                    <div className="text-xs" style={{ color: 'var(--text-3)' }}>{label}</div>
                    <div
                      className="mono text-sm font-medium"
                      style={{ color: accent || 'var(--text-2)' }}
                    >
                      {value ?? '—'}
                    </div>
                  </div>
                ))}
              </div>

              {log.error_message && (
                <p className="mt-1.5 text-xs p-2 rounded" style={{ background: '#2d1a1a', color: '#f87171' }}>
                  {log.error_message}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
