/**
 * Chart tokens.
 *
 * Recharts wants resolved values, but hardcoding them broke the moment a
 * second theme existed. Each token is a getter that reads the live CSS custom
 * property, so charts follow the active theme (and the active cert's accent)
 * for free — components re-render on theme change because the theme lives in
 * the app context, and every render re-reads these.
 */

import { useEffect, useRef, useState } from 'react'

const FALLBACK: Record<string, string> = {
  '--text': '#e4ecf4',
  '--text-dim': '#9fb0c3',
  '--text-mute': '#6b7c90',
  '--line': '#232e3c',
  '--grid': '#1f2936',
  '--surface': '#121820',
  '--raised': '#1c2531',
  '--accent': '#4dd0c7',
  '--good': '#46c46a',
  '--bad': '#f2615a',
  '--warn': '#e0a33a',
  '--band': 'rgba(159, 176, 195, 0.18)',
  '--d1': '#199e70',
  '--d2': '#d95926',
  '--d3': '#3987e5',
  '--d4': '#c98500',
  '--d5': '#d55181',
}

function cssVar(name: string): string {
  if (typeof window !== 'undefined') {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
    if (v) return v
  }
  return FALLBACK[name] ?? '#888888'
}

export const C = {
  get text() { return cssVar('--text') },
  get dim() { return cssVar('--text-dim') },
  get mute() { return cssVar('--text-mute') },
  get line() { return cssVar('--line') },
  get grid() { return cssVar('--grid') },
  get surface() { return cssVar('--surface') },
  get raised() { return cssVar('--raised') },
  get accent() { return cssVar('--accent') },
  get good() { return cssVar('--good') },
  get bad() { return cssVar('--bad') },
  get warn() { return cssVar('--warn') },
  get band() { return cssVar('--band') },
  get domains(): string[] {
    return [cssVar('--d1'), cssVar('--d2'), cssVar('--d3'), cssVar('--d4'), cssVar('--d5')]
  },
}

export function domainHue(id: string): string {
  const n = parseInt(id, 10)
  const domains = C.domains
  return domains[(Number.isFinite(n) ? n - 1 : 0) % domains.length]
}

/** Accuracy colour band, matching the CSS bar colours. */
export function accuracyHue(v: number | null): string {
  if (v == null) return C.mute
  return v < 0.55 ? C.bad : v < 0.75 ? C.warn : C.good
}

/** Container width, so hand-built SVG charts can lay out without distortion. */
export function useWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null)
  const [width, setWidth] = useState(720)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width
      if (w && Math.abs(w - width) > 1) setWidth(w)
    })
    ro.observe(el)
    setWidth(el.clientWidth || 720)
    return () => ro.disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return [ref, width]
}
