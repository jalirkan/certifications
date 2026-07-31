/**
 * Chart tokens.
 *
 * These duplicate the CSS custom properties as literals because Recharts
 * computes some geometry from colour props and SVG attributes are safer with
 * resolved values. Keep them in step with styles.css.
 */

import { useEffect, useRef, useState } from 'react'

export const C = {
  text: '#e4ecf4',
  dim: '#9fb0c3',
  mute: '#6b7c90',
  line: '#232e3c',
  grid: '#1f2936',
  surface: '#121820',
  raised: '#1c2531',
  accent: '#4dd0c7',
  good: '#46c46a',
  bad: '#f2615a',
  warn: '#e0a33a',
  band: 'rgba(159, 176, 195, 0.18)',
  domains: ['#4dd0c7', '#6f9bea', '#a888e0', '#e08fb4', '#e0b062'],
} as const

export function domainHue(id: string): string {
  const n = parseInt(id, 10)
  return C.domains[(Number.isFinite(n) ? n - 1 : 0) % C.domains.length]
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
