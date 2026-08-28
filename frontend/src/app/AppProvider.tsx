/**
 * App-wide context: the bootstrap payload, the selected certification and
 * profile, the theme, and toasts.
 *
 * Profile handling matters more than it looks. Results are per profile and the
 * bank is shared; mixing two learners into one history corrupts the scheduler
 * and every diagnostic. The selected profile is persisted per certification
 * (each cert keeps its own histories) and sent as X-Profile on every request;
 * the certification travels the same way as X-Cert. Switching either
 * refetches everything.
 *
 * The theme lives here rather than in CSS alone so charts re-render when it
 * flips: chart colors are read from the live CSS custom properties at render
 * time, and a context change re-renders every consumer.
 */

import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
  type ReactNode,
} from 'react'
import { api, setCert as setClientCert, setProfile as setClientProfile } from '../api/client'
import type { Bootstrap } from '../api/types'
import { Loading } from '../ui/primitives'

const CERT_KEY = 'study.cert'
const THEME_KEY = 'study.theme'

export type ThemeSetting = 'dark' | 'light' | 'auto'

/** Per-cert profile storage. The historical key for CISA was 'cisa.profile',
 *  which this scheme reproduces exactly, so nobody's selection is lost. */
const profileKey = (cert: string) => `${cert || 'cisa'}.profile`

function storedTheme(): ThemeSetting {
  const t = localStorage.getItem(THEME_KEY)
  return t === 'light' || t === 'auto' ? t : 'dark'
}

function resolveTheme(setting: ThemeSetting): 'dark' | 'light' {
  if (setting !== 'auto') return setting
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

interface AppCtx {
  boot: Bootstrap
  profile: string
  switchProfile: (name: string) => void
  /** Active certification folder id (e.g. "cisa", "cpa-aud"). */
  cert: string
  switchCert: (id: string) => void
  theme: ThemeSetting
  resolvedTheme: 'dark' | 'light'
  setTheme: (t: ThemeSetting) => void
  toast: (message: string, bad?: boolean) => void
  /** Bumped whenever the profile or cert changes, so screens can key their fetches. */
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
  const [cert, setCertState] = useState(() => localStorage.getItem(CERT_KEY) ?? '')
  const [profile, setProfileState] = useState(
    () => localStorage.getItem(profileKey(localStorage.getItem(CERT_KEY) ?? '')) ?? '',
  )
  const [theme, setThemeState] = useState<ThemeSetting>(storedTheme)
  const [resolvedTheme, setResolvedTheme] = useState<'dark' | 'light'>(() => resolveTheme(storedTheme()))
  const [boot, setBoot] = useState<Bootstrap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [toastState, setToastState] = useState<ToastState | null>(null)
  const timer = useRef<number | undefined>(undefined)

  // Set before any request goes out, including the first bootstrap.
  setClientProfile(profile)
  setClientCert(cert)

  const toast = useCallback((message: string, bad = false) => {
    setToastState({ message, bad, id: Date.now() })
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setToastState(null), 3400)
  }, [])

  useEffect(() => () => window.clearTimeout(timer.current), [])

  // Stamp the theme on <html> so the CSS tokens switch, and keep following the
  // OS while the setting is "auto".
  useEffect(() => {
    const apply = () => {
      const resolved = resolveTheme(theme)
      document.documentElement.dataset.theme = resolved
      setResolvedTheme(resolved)
    }
    apply()
    if (theme !== 'auto') return
    const mq = window.matchMedia('(prefers-color-scheme: light)')
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [theme])

  const setTheme = useCallback((t: ThemeSetting) => {
    localStorage.setItem(THEME_KEY, t)
    setThemeState(t)
  }, [])

  useEffect(() => {
    let live = true
    setClientProfile(profile)
    setClientCert(cert)
    // The accent follows the cert, so the room you are in is legible at a glance.
    if (cert) document.documentElement.dataset.cert = cert
    api.bootstrap().then(
      (data) => {
        if (!live) return
        setBoot(data)
        setError(null)
        document.title = data.cert_name || `${data.cert} study system`
        // First run with no stored choice: adopt the server's default cert so
        // the profile keys and accent are scoped correctly from here on.
        if (!cert) {
          const id = data.certs.find((c) => c.cert === data.cert)?.id
          if (id) document.documentElement.dataset.cert = id
        }
      },
      (err: unknown) => {
        if (live) setError(err instanceof Error ? err.message : String(err))
      },
    )
    return () => {
      live = false
    }
  }, [profile, cert])

  const switchProfile = useCallback(
    (name: string) => {
      const next = name.trim()
      localStorage.setItem(profileKey(cert), next)
      setClientProfile(next)
      setProfileState(next)
      setEpoch((n) => n + 1)
      toast(next ? `Studying as ${next}` : 'Using the shared profile')
    },
    [cert, toast],
  )

  const switchCert = useCallback(
    (id: string) => {
      const next = id.trim().toLowerCase()
      if (next === cert) return
      localStorage.setItem(CERT_KEY, next)
      const nextProfile = localStorage.getItem(profileKey(next)) ?? ''
      setClientCert(next)
      setClientProfile(nextProfile)
      setCertState(next)
      setProfileState(nextProfile)
      setEpoch((n) => n + 1)
    },
    [cert],
  )

  const value = useMemo<AppCtx | null>(
    () => (boot
      ? { boot, profile, switchProfile, cert, switchCert, theme, resolvedTheme, setTheme, toast, epoch }
      : null),
    [boot, profile, switchProfile, cert, switchCert, theme, resolvedTheme, setTheme, toast, epoch],
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
