// src/hooks/useApi.js
// Centralized API fetching hook with auto-refresh

import { useState, useEffect, useCallback } from 'react'

const BASE = '/api'

async function apiFetch(path, params = {}) {
  const url = new URL(BASE + path, window.location.origin)
  Object.entries(params).forEach(([k, v]) => v != null && url.searchParams.set(k, v))
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export function useApiData(path, params = {}, refreshMs = 0) {
  const [data,    setData]    = useState(undefined)
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState(null)

  const key = path + JSON.stringify(params)

  const load = useCallback(async () => {
    try {
      setError(null)
      const d = await apiFetch(path, params)
      setData(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => {
    load()
    if (refreshMs > 0) {
      const id = setInterval(load, refreshMs)
      return () => clearInterval(id)
    }
  }, [load, refreshMs])

  return { data, loading, error, reload: load }
}

export { apiFetch }
