/** Shared presentational pieces. Nothing here fetches or owns state. */

import type { ReactNode } from 'react'
import type { Interval } from '../api/types'
import { band, claim, hasEvidence, pct, rangeText } from '../lib/format'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`card ${className}`.trim()}>{children}</div>
}

export function Section({ children, hint }: { children: ReactNode; hint?: string }) {
  return (
    <h2 className="section">
      {children}
      {hint ? <span className="hint">{hint}</span> : null}
    </h2>
  )
}

export function Stat({
  label, value, foot, range,
}: {
  label: string
  value: ReactNode
  foot?: string
  range?: string
}) {
  return (
    <div className="stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
      {range ? <div className="range">{range}</div> : null}
      {foot ? <div className="foot">{foot}</div> : null}
    </div>
  )
}

export function Callout({
  children, kind = 'warn',
}: {
  children: ReactNode
  kind?: 'warn' | 'info' | 'bad'
}) {
  return <div className={`callout ${kind === 'warn' ? '' : kind}`.trim()}>{children}</div>
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Loading({ what = 'Loading…' }: { what?: string }) {
  return (
    <div className="loading">
      <span className="spinner" />
      {what}
    </div>
  )
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Callout kind="bad">
      <p>
        <b>Something went wrong.</b> {message}
      </p>
      {onRetry ? (
        <p>
          <button className="btn" onClick={onRetry} style={{ marginTop: 8 }}>
            Try again
          </button>
        </p>
      ) : null}
    </Callout>
  )
}

/**
 * A labelled accuracy bar with its Wilson interval drawn as a whisker.
 *
 * The whisker is not decoration: a wide one is the visual statement that the
 * sample is too small to claim anything. Under the evidence threshold the
 * right-hand figure becomes the range instead of a point estimate.
 */
export function BarRow({
  label, sub, stat, right, min,
}: {
  label: string
  sub?: string
  stat: Interval
  right?: ReactNode
  min?: number
}) {
  const { accuracy, low, high, attempts } = stat
  const width = accuracy == null ? 0 : accuracy * 100
  const showCi = low != null && high != null && high > low && attempts > 0
  const confident = hasEvidence(attempts, min)

  return (
    <div className="bar-row">
      <div className="bar-label">
        {label}
        {sub ? <small>{sub}</small> : null}
      </div>
      <div
        className="track"
        role="img"
        aria-label={
          attempts
            ? `${pct(accuracy)}, 95% confidence ${rangeText(low, high)}, ${attempts} answered`
            : 'no data'
        }
      >
        <div className={`fill ${band(accuracy)}`.trim()} style={{ width: `${width.toFixed(1)}%` }} />
        {showCi ? (
          <div
            className="ci"
            style={{
              left: `${(low * 100).toFixed(1)}%`,
              width: `${((high - low) * 100).toFixed(1)}%`,
            }}
          />
        ) : null}
      </div>
      <div className="bar-num">
        {right ?? (
          confident ? claim(stat, min) : <span className="unknown">{claim(stat, min)}</span>
        )}
      </div>
    </div>
  )
}

export function Chip({
  children, kind, mono,
}: {
  children: ReactNode
  kind?: 'good' | 'bad' | 'warn'
  mono?: boolean
}) {
  return (
    <span className={['chip', kind ?? '', mono ? 'mono' : ''].filter(Boolean).join(' ')}>
      {children}
    </span>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  )
}

export function Seg<T extends string>({
  value, options, onChange,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}) {
  return (
    <div className="seg" role="group">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={o.value === value ? 'on' : ''}
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
