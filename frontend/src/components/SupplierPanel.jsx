// src/components/SupplierPanel.jsx
import { useApiData } from '../hooks/useApi'
import { criticalityColor } from '../utils'
import { Shield } from 'lucide-react'

const TIER_LABEL = { 1: 'Direct', 2: 'Sub-tier', 3: 'Raw Material' }
const CRIT_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

export default function SupplierPanel() {
  const { data, loading } = useApiData('/suppliers/', {}, 120000)
  const suppliers = data || []

  const sorted = [...suppliers].sort(
    (a, b) => (CRIT_ORDER[a.criticality] ?? 9) - (CRIT_ORDER[b.criticality] ?? 9)
  )

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '10px 16px', borderBottom: '1px solid var(--surface-3)', flexShrink: 0,
      }}>
        <Shield size={12} style={{ color: 'var(--amber)' }} />
        <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 11, fontWeight: 500, color: 'var(--amber)' }}>
          SUPPLIER NETWORK
        </span>
        <span style={{ marginLeft: 'auto', fontFamily: 'DM Mono, monospace', fontSize: 11, color: 'var(--text-3)' }}>
          {suppliers.length} tracked
        </span>
      </div>

      <div style={{ overflowY: 'auto', flex: 1 }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 80, fontSize: 13, color: 'var(--text-3)' }}>
            Loading…
          </div>
        )}

        {[1, 2, 3].map(tier => {
          const group = sorted.filter(s => s.tier === tier)
          if (!group.length) return null
          return (
            <div key={tier}>
              {/* Tier header */}
              <div style={{
                padding: '6px 16px', fontSize: 10,
                fontFamily: 'DM Mono, monospace', fontWeight: 500,
                textTransform: 'uppercase', letterSpacing: '0.06em',
                background: 'var(--surface-2)', color: 'var(--text-3)',
                position: 'sticky', top: 0,
              }}>
                Tier {tier} — {TIER_LABEL[tier]}
              </div>

              {group.map(s => (
                <div key={s.id} style={{
                  padding: '10px 20px',
                  borderBottom: '1px solid var(--surface-3)',
                }}>
                  {/* Name row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{
                      width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
                      background: criticalityColor(s.criticality),
                    }} />
                    <span style={{ fontSize: 13, fontWeight: 500, flex: 1, color: 'var(--text-1)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.name}
                    </span>
                    <span style={{
                      fontFamily: 'DM Mono, monospace', fontSize: 10,
                      textTransform: 'uppercase', letterSpacing: '0.04em',
                      color: criticalityColor(s.criticality), flexShrink: 0,
                    }}>
                      {s.criticality}
                    </span>
                  </div>

                  {/* Commodity + bar row */}
                  <div style={{ paddingLeft: 15 }}>
                    <p style={{ fontSize: 11, color: 'var(--text-3)', margin: '0 0 6px 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {s.commodity?.split('(')[0].trim()}
                    </p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--text-3)', flexShrink: 0 }}>
                        {s.country_code}
                      </span>
                      {s.dependency_weight > 0 && (
                        <>
                          <div style={{ flex: 1, maxWidth: 72, height: 4, borderRadius: 2, background: 'var(--surface-3)', overflow: 'hidden' }}>
                            <div style={{
                              width: `${s.dependency_weight * 100}%`, height: '100%',
                              borderRadius: 2, background: criticalityColor(s.criticality), opacity: 0.75,
                            }} />
                          </div>
                          <span style={{ fontFamily: 'DM Mono, monospace', fontSize: 10, color: 'var(--text-3)' }}>
                            {Math.round(s.dependency_weight * 100)}%
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}
