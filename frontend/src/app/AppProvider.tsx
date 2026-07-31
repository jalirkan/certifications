/**
 * App-wide context: the bootstrap payload, the selected profile, and toasts.
 *
 * Profile handling matters more than it looks. Results are per profile and the
 * bank is shared; mixing two learners into one history corrupts the scheduler
 * and every diagnostic. The selected profile is persisted to localStorage and
 * sent as X-Profile on every request, and switching it refetches everything.
 */

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react'
import { api, setProfile as setClientProfile } from '../api/client'
import type { Bootstrap } from '../api/types'
import { Loading } from '../ui/primitives'

const STORAGE_KEY = 'cisa.profile'

interface AppCtx {
  boot: Bootstrap
  profile: string
  switchProfile: (name: string) => void
  toast: (message: string, bad?: boolean) => void
  /** Bumped whenever the profile changes, so screens can key their fetches. */
  epoch: number
}

const Ctx = createContext<AppCtx | null>(null)

export function useApp(): AppCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useApp used outside AppProvider')
  return ctx
}

interface ToastState {
  message: string
  bad: boolean
  id: number
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState(
    () => localStorage.getItem(STORAGE_KEY) ?? '',
  )
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [toastState, setToastState] = useState<ToastState | null>(null)
  const timer = useRef<number | undefined>(undefined)

  // Set before any request goes out, including the first bootstrap.
  setClientProfile(profile)

  const toast = useCallback((message: string, bad = false) => {
    setToastState({ message, bad, id: Date.now() })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setToastState(null), 3400)
  }, [])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  useEffect(() => {
    let live = true
    setClientProfile(profile)
    api.bootstrap().then(
      (data) => {
        if (!live) return
        setBoot(data)
        setError(null)
      },
      (err: unknown) => {
        if (live) setError(err instanceof Error ? err.message : String(err))
      },
    )
    return () => {
      live = false
    }
  }, [profile])

  const switchProfile = useCallback(
    (name: string) => {
      const next = name.trim()
      localStorage.setItem(STORAGE_KEY, next)
      setClientProfile(next)
      setProfileState(next)
      setEpoch((n) => n + 1)
      toast(next ? `Studying as ${next}` : 'Using the shared profile')
    },
    [toast],
  )

  const value = useMemo<AppCtx | null>(
    () => (boot ? { boot, profile, switchProfile, toast, epoch } : null),
    [boot, profile, switchProfile, toast, epoch],
  )

  if (error) {
    return (
      <div className="wrap">
        <div className="callout bad">
          <p><b>Could not reach the study server.</b> {error}</p>
          <p>Start it with <code className="mono">python serve.py</code> and reload.</p>
        </div>
      </div>
    )
  }
  if (!value) return <Loading what="Loading question bank…" />

  return (
    <Ctx.Provider value={value}>
      {children}
      {toastState ? (
        <div
          className={`toast ${toastState.bad ? 'bad' : ''}`.trim()}
          role="status"
          aria-live="polite"
        >
          {toastState.message}
        </div>
      ) : null}
    </Ctx.Provider>
  )
}
