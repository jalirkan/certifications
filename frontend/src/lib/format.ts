/**
 * Formatting helpers.
 *
 * The interval helpers are the important ones. Project rule: every statistic
 * carries its uncertainty, and a small sample must visibly read as "unknown"
 * rather than as a confident number. 2 out of 2 is not 100%, it is 34-100%.
 * Centralising that here means no screen can quietly opt out of it.
 */

import type { Interval } from '../api/types'

/** Below this many attempts, a point estimate is noise and is not shown as one. */
export const MIN_CLAIM = 5

export const LETTERS = ['A', 'B', 'C', 'D'] as const

export function pct(v: number | null | undefined, digits = 0): string {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`
}

export function num(v: number | null | undefined): string {
  return v == null ? '—' : String(v)
}

/** "34–100%" — the honest rendering of a small sample. */
export function rangeText(low: number | null, high: number | null): string {
  if (low == null || high == null) return 'no data'
  return `${Math.round(low * 100)}–${Math.round(high * 100)}%`
}

/** True when there is enough evidence to state a point estimate at all. */
export function hasEvidence(attempts: number, min = MIN_CLAIM): boolean {
  return attempts >= min
}

/**
 * Wilson score interval, mirroring drillkit/itemanalysis.py:wilson_interval.
 *
 * Duplicated here only for figures the API reports without bounds - chiefly the
 * headline overall accuracy. The naive interval would say 2/2 is 100% with no
 * uncertainty, which is exactly the wrong conclusion from two attempts, and the
 * project rule is that no statistic is shown without one.
 */
export function wilson(correct: number, n: number, z = 1.96): [number, number] {
  if (n <= 0) return [0, 1]
  const p = correct / n
  const denom = 1 + (z * z) / n
  const centre = (p + (z * z) / (2 * n)) / denom
  const margin = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / denom
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)]
}

/** Build an Interval for a bucket the API reports as bare counts. */
export function intervalOf(correct: number, attempts: number): Interval {
  const [low, high] = wilson(correct, attempts)
  return {
    accuracy: attempts ? correct / attempts : null,
    attempts,
    low: attempts ? low : null,
    high: attempts ? high : null,
  }
}

/**
 * What to print as the headline figure for a bucket.
 * Under the threshold the range replaces the percentage, so the uncertainty is
 * the number rather than a footnote next to it.
 */
export function claim(stat: Interval, min = MIN_CLAIM): string {
  if (!stat.attempts) return '—'
  if (!hasEvidence(stat.attempts, min)) return rangeText(stat.low, stat.high)
  return pct(stat.accuracy)
}

export function hms(sec: number): string {
  const s = Math.max(0, Math.round(sec))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const r = s % 60
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
    : `${m}:${String(r).padStart(2, '0')}`
}

/** Colour band for a bar. Null (no data) is deliberately unbanded. */
export function band(v: number | null): '' | 'low' | 'mid' | 'high' {
  if (v == null) return ''
  return v < 0.55 ? 'low' : v < 0.75 ? 'mid' : 'high'
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return n === 1 ? one : many
}

/** "2026-07-31T09:12:00+01:00" -> "2026-07-31 09:12" */
export function stamp(iso: string): string {
  return (iso || '').slice(0, 16).replace('T', ' ')
}

/** "2026-07-31" -> "31 Jul" for chart axes. */
export function shortDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

export const DOMAIN_COLORS = [
  'var(--d1)', 'var(--d2)', 'var(--d3)', 'var(--d4)', 'var(--d5)',
] as const

export function domainColor(id: string): string {
  const n = parseInt(id, 10)
  return DOMAIN_COLORS[(Number.isFinite(n) ? n - 1 : 0) % DOMAIN_COLORS.length]
}
