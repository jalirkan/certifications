/**
 * Where the hundred blueprint points went.
 *
 * `cost` — accuracy gap times exam weight — is the most actionable number the
 * exam produces, and it used to render as a sorted list of rows: the one shape
 * that hides what it is. It is a decomposition. A hundred points are on the
 * table, each domain takes some away, and what survives is what was earned.
 *
 * The thing this makes visible in one look, and a list does not: a domain can
 * be your *worst* by accuracy and cost almost nothing, because Domain 3 is 12%
 * of the exam and Domain 4 is 26%. Sorted by accuracy, D3 leads and you study
 * the wrong thing.
 *
 * Built as a stacked bar with a transparent base rather than hand-rolled SVG —
 * the base carries the running balance, the visible segment is the drop. Each
 * drop carries the interval on its own accuracy, so two bars whose whiskers
 * overlap are visibly *not* rankable against each other, which on a 150-item
 * sitting is most adjacent pairs.
 */

import {
  Bar, BarChart, CartesianGrid, Cell, ErrorBar, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { WaterfallStep } from '../api/types'
import { C, domainHue } from './theme'

interface Row {
  key: string
  label: string
  base: number
  drop: number
  err: [number, number]
  step: WaterfallStep | null
  kind: 'available' | 'domain' | 'earned'
}

function build(steps: WaterfallStep[], available: number, earned: number): Row[] {
  const rows: Row[] = [{
    key: 'available', label: 'Available', base: 0, drop: available,
    err: [0, 0], step: null, kind: 'available',
  }]
  for (const s of steps) {
    rows.push({
      key: s.domain,
      label: `D${s.domain}`,
      base: s.to,
      drop: s.cost,
      err: [
        Math.max(0, s.cost - (s.cost_low ?? s.cost)),
        Math.max(0, (s.cost_high ?? s.cost) - s.cost),
      ],
      step: s,
      kind: 'domain',
    })
  }
  rows.push({
    key: 'earned', label: 'Earned', base: 0, drop: earned,
    err: [0, 0], step: null, kind: 'earned',
  })
  return rows
}

function Note({ row }: { row: Row }) {
  if (row.kind === 'available') {
    return <div className="s">The whole blueprint, before anything is lost.</div>
  }
  if (row.kind === 'earned') {
    return <div className="s">Blueprint weight you held on to.</div>
  }
  const s = row.step!
  return (
    <>
      <div className="s">
        {s.correct}/{s.asked} correct · {s.weight}% of the exam
      </div>
      <div className="s">
        cost {s.cost.toFixed(1)} points
        {s.cost_low != null && s.cost_high != null
          ? ` (95% CI ${s.cost_low.toFixed(1)}–${s.cost_high.toFixed(1)})`
          : ''}
        {s.enough ? '' : ' — too few asked to rank confidently'}
      </div>
    </>
  )
}

export function Waterfall({ steps, available, earned }: {
  steps: WaterfallStep[]
  available: number
  earned: number
}) {
  const rows = build(steps, available, earned)

  return (
    <div className="waterfall">
      <div style={{ width: '100%', height: 260 }}>
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid stroke={C.grid} vertical={false} />
            <XAxis dataKey="label" stroke={C.mute} tickLine={false}
                   axisLine={{ stroke: C.line }} fontSize={12} />
            <YAxis stroke={C.mute} tickLine={false} axisLine={false} fontSize={12}
                   domain={[0, Math.ceil(available / 10) * 10]}
                   label={{ value: 'blueprint %', angle: -90, position: 'insideLeft',
                            fill: C.mute, fontSize: 11 }} />
            <ReferenceLine y={earned} stroke={C.line} strokeDasharray="4 4" />
            <Tooltip
              cursor={{ fill: 'rgba(255,255,255,.03)' }}
              contentStyle={{ background: C.raised, border: `1px solid ${C.line}`,
                              borderRadius: 8, fontSize: 12.5 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const row = payload[0].payload as Row
                return (
                  <div className="chart-tip">
                    <b>{row.step ? `D${row.step.domain} ${row.step.name}` : row.label}</b>
                    <Note row={row} />
                  </div>
                )
              }} />
            {/* Invisible plinth carrying the running balance. */}
            <Bar dataKey="base" stackId="w" fill="transparent" isAnimationActive={false} />
            <Bar dataKey="drop" stackId="w" radius={[3, 3, 0, 0]} isAnimationActive={false}>
              {rows.map((row) => (
                <Cell key={row.key}
                      fill={row.kind === 'domain' ? C.bad
                            : row.kind === 'earned' ? C.good : C.line} />
              ))}
              <ErrorBar dataKey="err" width={5} strokeWidth={1.4} stroke={C.dim} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="wf-rows">
        {steps.map((s) => (
          <div className="list-row" key={s.domain}>
            <span className="wf-swatch" style={{ background: domainHue(s.domain) }} />
            <div className="grow">
              <div className="t">D{s.domain} {s.name}</div>
              <div className="s">
                {s.accuracy == null ? 'not asked'
                  : `${Math.round(s.accuracy * 100)}% of ${s.asked} · ${s.weight}% of the exam`}
                {/* Thin sampling has to be visible without hovering: on a
                    20-question sitting every domain is thin, and the ranking
                    between them means nothing. */}
                {s.asked && !s.enough
                  ? <span className="wf-thin">too few asked to rank</span>
                  : null}
              </div>
            </div>
            <div className="right">
              <div className="t" style={{ color: s.cost > 0 ? 'var(--bad)' : 'var(--text-mute)' }}>
                −{s.cost.toFixed(1)}
              </div>
              <div className="s">
                {s.cost_low != null && s.cost_high != null
                  ? `${s.cost_low.toFixed(1)}–${s.cost_high.toFixed(1)}`
                  : '—'}
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="chart-note">
        Points are blueprint weight, not marks: a domain worth 26% of the exam can
        cost more at 70% accuracy than a 12% domain costs at 50%. Whiskers are the
        95% interval on this sitting's sample — where two overlap, this exam does
        not settle which of the two cost you more.
      </p>
    </div>
  )
}
