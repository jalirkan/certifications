/** Small hooks shared across screens. */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Fetch on mount and whenever `deps` change; expose a manual reload. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [nonce, setNonce] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    fnRef.current().then(
      (result) => {
        if (!live) return
        setData(result)
        setLoading(false)
      },
      (err: unknown) => {
        if (!live) return
        setError(err instanceof ApiError ? err.message : String(err))
        setLoading(false)
      },
    )
    return () => {
      live = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { data, error, loading, reload }
}

/**
 * Window-level key handler that stands down while the user is typing in a
 * field, so A-D shortcuts never eat input in the drill filters.
 */
export function useKeys(handler: (ev: KeyboardEvent) => void, enabled = true): void {
  const ref = useRef(handler)
  ref.current = handler

  useEffect(() => {
    if (!enabled) return
    const onKey = (ev: KeyboardEvent) => {
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return
      const el = document.activeElement
      const tag = el?.tagName ?? ''
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (el instanceof HTMLElement && el.isContentEditable) return
      ref.current(ev)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [enabled])
}

/** Milliseconds since the value of `key` last changed, as a stopwatch start. */
export function useStopwatch(key: unknown): () => number {
  const start = useRef(Date.now())
  useEffect(() => {
    start.current = Date.now()
  }, [key])
  return useCallback(() => (Date.now() - start.current) / 1000, [])
}
