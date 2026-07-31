/**
 * Accuracy by domain, with bar width proportional to exam weight.
 *
 * This is a Marimekko, not a bar chart, and the difference is the whole point:
 * the horizontal axis is share of the exam, so the *area* of each bar maps to
 * marks available rather than to how many topics happen to sit in that domain.
 * D4 and D5 are 26% each and visibly dominate; D3 is 12% and visibly does not.
 *
 * Hand-built rather than Recharts because no mainstream chart library does
 * variable-width bars, and faking it with stacked categories loses the axis.
 *
 * Every bar carries its Wilson interval as a vertical whisker. Domains with too
 * little evidence are drawn as outlines rather than solid fills, so "I have not
 * tested this yet" never reads as "I am bad at this".
 */

import { useState } from 'react'
import type { DomainStat } from '../api/types'
import { hasEvidence, pct, rangeText } from '../lib/format'
import { accuracyHue, C, useWidth } from './theme'

const H = 290
const PAD = { top: 16, right: 14, bottom: 54, left: 46 }

export function DomainAccuracyChart({ domains }: { domains: DomainStat[] }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)

  const innerW = Math.max(120, width - PAD.left - PAD.right)
  const innerH = H - PAD.top - PAD.bottom
  const totalWeight = domains.reduce((s, d) => s + (d.weight || 0), 0) || 1
  const y = (v: number) => PAD.top + innerH * (1 - v)

  let cursor = PAD.left
  const bars = domains.map((d) => {
    const w = ((d.weight || 0) / totalWeight) * innerW
    const bar = { d, x: cursor, w }
    cursor += w
    return bar
  })

  const anyData = domains.some((d) => d.attempts > 0)
  const active = hover == null ? null : bars[hover]

  return (
    <div className="chart-wrap" ref={ref} style={{ position: 'relative' }}>
      <svg width="100%" height={H} role="img"
           aria-label="Accuracy by domain, bar width proportional to exam weight, with 95% confidence intervals">
        {/* horizontal gridlines */}
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={PAD.left} x2={PAD.left + innerW} y1={y(t)} y2={y(t)}
                  stroke={C.grid} strokeWidth={1} />
            <text x={PAD.left - 9} y={y(t) + 4} textAnchor="end"
                  fontSize={11} fill={C.mute}>{Math.round(t * 100)}%</text>
          </g>
        ))}

        {bars.map((b, i) => {
          const { d } = b
          const gap = Math.min(6, b.w * 0.08)
          const x = b.x + gap / 2
          const w = Math.max(1, b.w - gap)
          const hue = accuracyHue(d.accuracy)
          const solid = d.attempts > 0 && hasEvidence(d.attempts)
          const mid = x + w / 2

          return (
            <g key={d.id}
               onMouseEnter={() => setHover(i)}
               onMouseLeave={() => setHover((h) => (h === i ? null : h))}>
              {/* full-height hit area keeps the hover target generous */}
              <rect x={b.x} y={PAD.top} width={b.w} height={innerH}
                    fill={hover === i ? 'rgba(255,255,255,.03)' : 'transparent'} />

              {d.accuracy != null ? (
                <rect
                  x={x} y={y(d.accuracy)} width={w} height={innerH - (y(d.accuracy) - PAD.top)}
                  fill={solid ? hue : 'transparent'}
                  fillOpacity={solid ? 0.82 : 1}
                  stroke={hue}
                  strokeWidth={solid ? 0 : 1.5}
                  strokeDasharray={solid ? undefined : '4 3'}
                  rx={2}
                />
              ) : (
                <text x={mid} y={y(0.06)} textAnchor="middle" fontSize={11} fill={C.mute}>
                  no data
                </text>
              )}

              {/* Wilson interval. A tall whisker is the chart saying "unknown". */}
              {d.attempts > 0 && d.low != null && d.high != null ? (
                <g stroke={C.text} strokeWidth={1.25} opacity={0.85}>
                  <line x1={mid} x2={mid} y1={y(d.low)} y2={y(d.high)} />
                  <line x1={mid - 5} x2={mid + 5} y1={y(d.high)} y2={y(d.high)} />
                  <line x1={mid - 5} x2={mid + 5} y1={y(d.low)} y2={y(d.low)} />
                </g>
              ) : null}

              {/* axis labels */}
              <text x={mid} y={H - PAD.bottom + 19} textAnchor="middle"
                    fontSize={12} fill={hover === i ? C.text : C.dim}>
                D{d.id}
              </text>
              <text x={mid} y={H - PAD.bottom + 34} textAnchor="middle"
                    fontSize={10.5} fill={C.mute}>
                {d.weight}%
              </text>
            </g>
          )
        })}

        <line x1={PAD.left} x2={PAD.left + innerW} y1={y(0)} y2={y(0)}
              stroke={C.line} strokeWidth={1} />
        <text x={PAD.left + innerW / 2} y={H - 6} textAnchor="middle"
              fontSize={11} fill={C.mute}>
          bar width = share of the exam
        </text>
      </svg>

      {active ? (
        <div
          className="tip"
          style={{
            position: 'absolute',
            left: Math.min(Math.max(active.x + active.w / 2 - 110, 0), Math.max(0, width - 230)),
            top: 4,
            pointerEvents: 'none',
          }}
        >
          <div className="t">D{active.d.id} {active.d.name}</div>
          <div className="r">
            {active.d.attempts
              ? `${pct(active.d.accuracy)} · 95% CI ${rangeText(active.d.low, active.d.high)}`
              : 'nothing answered yet'}
          </div>
          <div className="s">
            {active.d.weight}% of the exam · {active.d.attempts} answered ·{' '}
            {active.d.questions} in bank
          </div>
        </div>
      ) : null}

      {!anyData ? (
        <p className="chart-note">
          Nothing answered yet. Bars appear as you drill; the whiskers start wide and
          tighten as the evidence accumulates.
        </p>
      ) : null}
    </div>
  )
}
