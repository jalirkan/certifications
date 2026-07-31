/**
 * Decision-rule diagnostic as a ranked dot plot with interval whiskers.
 *
 * 22 rules is too many for stacked bars - they become a wall of colour with no
 * ordering to read. A dot plot ranks cleanly, and the whisker does the honest
 * work: rules you have barely tested show as a dot with a very wide interval,
 * which reads as "unknown" rather than "weak".
 *
 * Recharts earns its place here: Scatter + ErrorBar handles the whiskers,
 * category axis and tooltips without hand-rolling any of it.
 */

import {
  CartesianGrid, Cell, ErrorBar, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { RuleStat } from '../api/types'
import { hasEvidence, pct, rangeText } from '../lib/format'
import { accuracyHue, C } from './theme'

interface Row {
  name: string
  accuracy: number
  err: [number, number]
  stat: RuleStat
}

function truncate(s: string, n = 34): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

function RuleTip({ active, payload }: {
  active?: boolean
  payload?: { payload: Row }[]
}) {
  if (!active || !payload?.length) return null
  const { stat } = payload[0].payload
  return (
    <div className="tip">
      <div className="t">{stat.name}</div>
      <div className="r">
        {hasEvidence(stat.attempts)
          ? `${pct(stat.accuracy)} · 95% CI ${rangeText(stat.low, stat.high)}`
          : `${rangeText(stat.low, stat.high)} — too few to call`}
      </div>
      <div className="s">
        {stat.attempts} answered · {stat.seen}/{stat.total} questions seen
      </div>
    </div>
  )
}

export function RuleDotPlot({ rules }: { rules: RuleStat[] }) {
  const rows: Row[] = rules
    .filter((r) => r.attempts > 0 && r.accuracy != null)
    .map((r) => ({
      name: truncate(r.name),
      accuracy: r.accuracy as number,
      err: [
        Math.max(0, (r.accuracy as number) - (r.low ?? 0)),
        Math.max(0, (r.high ?? 1) - (r.accuracy as number)),
      ],
      stat: r,
    }))

  if (!rows.length) {
    return (
      <p className="chart-note">
        No rule has been tested yet. Answer around 20 questions and this ranks
        every rule weakest first, with the interval showing how much to trust it.
      </p>
    )
  }

  const height = Math.max(180, rows.length * 26 + 54)

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart layout="vertical" margin={{ top: 6, right: 22, bottom: 22, left: 4 }}>
          <CartesianGrid stroke={C.grid} horizontal={false} />
          <XAxis
            type="number"
            dataKey="accuracy"
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fill: C.mute, fontSize: 11 }}
            stroke={C.line}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={210}
            tick={{ fill: C.dim, fontSize: 11.5 }}
            stroke={C.line}
            interval={0}
          />
          <ReferenceLine
            x={0.75}
            stroke={C.mute}
            strokeDasharray="3 3"
            label={{ value: 'target', position: 'top', fill: C.mute, fontSize: 10 }}
          />
          <Tooltip content={<RuleTip />} cursor={{ stroke: C.line }} />
          <Scatter data={rows} fill={C.accent} shape="circle" isAnimationActive={false}>
            <ErrorBar dataKey="err" direction="x" width={4} strokeWidth={1.2} stroke={C.dim} />
            {rows.map((r) => (
              <Cell key={r.stat.id} fill={accuracyHue(r.accuracy)} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Dot is the point estimate; the bar through it is the 95% confidence interval.
        A long bar means the rule has not been tested enough to draw a conclusion.
      </p>
    </div>
  )
}
