// src/utils.js

export function timeAgo(isoStr) {
  if (!isoStr) return '—'
  const diff = Date.now() - new Date(isoStr).getTime()
  const m = Math.floor(diff / 60000)
  const h = Math.floor(m / 60)
  const d = Math.floor(h / 24)
  if (d > 0) return `${d}d ago`
  if (h > 0) return `${h}h ago`
  if (m > 0) return `${m}m ago`
  return 'just now'
}

export function fmtNum(n) {
  if (n == null) return '—'
  return n.toLocaleString()
}

export function riskColor(band) {
  const map = {
    critical: '#ef4444', CRITICAL: '#ef4444',
    high:     '#f97316', HIGH:     '#f97316',
    medium:   '#eab308', MEDIUM:   '#eab308',
    low:      '#3b82f6', LOW:      '#3b82f6',
    watch:    '#6b7280', WATCH:    '#6b7280',
  }
  return map[band] || '#6b7280'
}

export function criticalityColor(c) {
  const map = {
    critical: '#ef4444',
    high:     '#f97316',
    medium:   '#eab308',
    low:      '#6b7280',
  }
  return map[c] || '#6b7280'
}

export function trackLabel(fetch_type) {
  return fetch_type === 'targeted' ? 'A' : 'B'
}

export function truncate(str, len = 120) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '…' : str
}
