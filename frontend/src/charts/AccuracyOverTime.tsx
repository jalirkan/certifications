/**
 * Accuracy over time, from the timestamped attempt log.
 *
 * Two views, because they answer different questions and one line would
 * conflate them:
 *
 *   Cumulative - accuracy over everything answered up to that day, drawn with
 *   its Wilson band. The band starts wide and narrows, which is the honest
 *   picture of how much you actually know about yourself yet.
 *
 *   Last N days - a trailing window that moves when recent work differs from
 *   the record, at the cost of being noisy on light study days.
 *
 * Per-domain lines are opt-in and only drawn once a domain has enough attempts
 * to be worth a line at all; below that they would be noise wearing a trend's
 * clothing.
 */

import { useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import type { Trend } from '../api/types'
import { MIN_CLAIM, pct, rangeText, shortDate } from '../lib/format'
import { C, domainHue } from './theme'

type View = 'cum' | 'roll'

interface Point {
  date: string
  label: string
  value: number | null
  band: [number, number] | null
  attempts: number
  correct: number
  low: number | null
  high: number | null
  [domainKey: string]: unknown
}

function TrendTip({ active, payload, label, view, window }: {
  active?: boolean
  payload?: { payload: Point }[]
  label?: string
  view: View
  window: number
}) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tip">
      <div className="t">{label}</div>
      {p.value == null ? (
        <div className="s">nothing answered in this window</div>
      ) : (
        <>
          <div className="r">
            {pct(p.value)} · 95% CI {rangeText(p.low, p.high)}
          </div>
          <div className="s">
            {p.correct}/{p.attempts} {view === 'cum' ? 'all time' : `in the last ${window} days`}
          </div>
        </>
      )}
    </div>
  )
}

export function AccuracyOverTime({ trend }: { trend: Trend }) {
  const [view, setView] = useState<View>('cum')
  const [showDomains, setShowDomains] = useState(false)

  if (!trend.points.length) {
    return (
      <p className="chart-note">
        No answers logged yet. This charts accuracy as it accumulates, with the
        confidence band narrowing as the evidence grows.
      </p>
    )
  }

  // Only chart a domain once it has enough attempts to mean anything.
  const last = trend.points[trend.points.length - 1]
  const liveDomains = trend.domains.filter(
    (d) => (last.domains[d.id]?.attempts ?? 0) >= MIN_CLAIM,
  )

  const data: Point[] = trend.points.map((p) => {
    const value = view === 'cum' ? p.cum_accuracy : p.roll_accuracy
    const low = view === 'cum' ? p.cum_low : p.roll_low
    const high = view === 'cum' ? p.cum_high : p.roll_high
    const row: Point = {
      date: p.date,
      label: shortDate(p.date),
      value,
      band: low != null && high != null ? [low, high] : null,
      attempts: view === 'cum' ? p.cum_attempts : p.roll_attempts,
      correct: view === 'cum' ? p.cum_correct : p.roll_correct,
      low,
      high,
    }
    for (const d of liveDomains) {
      row[`d${d.id}`] = p.domains[d.id]?.accuracy ?? null
    }
    return row
  })

  return (
    <div className="chart-wrap">
      <div className="btn-row" style={{ marginBottom: 10 }}>
        <div className="seg">
          <button className={view === 'cum' ? 'on' : ''} onClick={() => setView('cum')}>
            Cumulative
          </button>
          <button className={view === 'roll' ? 'on' : ''} onClick={() => setView('roll')}>
            Last {trend.window} days
          </button>
        </div>
        {liveDomains.length ? (
          <button
            className={`btn ghost ${showDomains ? '' : ''}`}
            onClick={() => setShowDomains((s) => !s)}
          >
            {showDomains ? 'Hide' : 'Show'} per-domain
          </button>
        ) : null}
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 8, right: 14, bottom: 4, left: -14 }}>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: C.mute, fontSize: 11 }}
            stroke={C.line}
            minTickGap={28}
          />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fill: C.mute, fontSize: 11 }}
            stroke={C.line}
          />
          <Tooltip content={<TrendTip view={view} window={trend.window} />} />

          {/* The interval band is drawn first so the line sits on top of it. */}
          <Area
            dataKey="band"
            stroke="none"
            fill={C.band}
            isAnimationActive={false}
            connectNulls={false}
            name="95% confidence"
            legendType="none"
          />
          <Line
            dataKey="value"
            stroke={C.accent}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
            name="Overall"
          />

          {showDomains
            ? liveDomains.map((d) => (
                <Line
                  key={d.id}
                  dataKey={`d${d.id}`}
                  stroke={domainHue(d.id)}
                  strokeWidth={1.3}
                  dot={false}
                  isAnimationActive={false}
                  connectNulls
                  name={`D${d.id} ${d.name}`}
                />
              ))
            : null}

          {showDomains ? (
            <Legend wrapperStyle={{ fontSize: 11.5, color: C.dim }} iconType="plainline" />
          ) : null}
        </ComposedChart>
      </ResponsiveContainer>

      <p className="chart-note">
        {view === 'cum'
          ? 'Shaded band is the 95% confidence interval on everything answered so far. It narrows as evidence accumulates — early movement is mostly noise.'
          : `Trailing ${trend.window}-day window. More responsive than the cumulative line, and much noisier on light study days.`}
        {liveDomains.length < trend.domains.length
          ? ` Domains with fewer than ${MIN_CLAIM} attempts are left off.`
          : ''}
      </p>
    </div>
  )
}
