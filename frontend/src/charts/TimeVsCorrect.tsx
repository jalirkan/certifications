/**
 * Seconds against correctness — the view of a sitting nothing else shows.
 *
 * `seconds_per_question` has been stored since the exam runner was written and
 * has never reached a screen. The quadrant worth knowing is **fast and wrong**:
 * answered below your own median pace, and missed. Rushing and not knowing
 * produce the same mark and want opposite fixes.
 *
 * Two strips rather than a cloud. Every question sits on the seconds axis, on
 * the "missed" row or the "correct" row, with the median drawn through both.
 * A cluster low-left on the missed row is the finding; a scatter with a y-axis
 * of nothing would bury it in overplotting.
 *
 * **The split is the learner's own median for this sitting**, never a fixed
 * number of seconds — "fast" only means anything relative to how they were
 * working that day.
 *
 * **It states an association and refuses to name a cause.** You go fast on
 * questions that *look* easy, so fast-and-wrong is as consistent with
 * misjudging difficulty as with hurrying, and if one domain is both weak and
 * quick then the split is really measuring that domain. That is why the
 * waterfall sits directly above this on the page: it is what tells them apart.
 */

import {
  CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis, ZAxis,
} from 'recharts'
import type { Timing, TimingPoint } from '../api/types'
import { C, domainHue } from './theme'
import { BarRow } from '../ui/primitives'
import { intervalOf } from '../lib/format'

const ROW = { missed: 0, correct: 1 }

/** Deterministic vertical jitter, so overlapping points stay countable. */
function jitter(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 1000
  return (h / 1000 - 0.5) * 0.42
}

export function TimeVsCorrect({ timing, verdict }: {
  timing: Timing
  verdict: string | null
}) {
  if (timing.median == null) {
    return (
      <p className="chart-note">
        No per-question timings were recorded for this sitting, so there is
        nothing to compare pace against.
      </p>
    )
  }

  const shape = (p: TimingPoint) => ({
    x: p.seconds,
    y: (p.correct ? ROW.correct : ROW.missed) + jitter(p.id),
    point: p,
  })
  const correct = timing.points.filter((p) => p.correct).map(shape)
  const missed = timing.points.filter((p) => !p.correct).map(shape)

  return (
    <div className="timing">
      <div style={{ width: '100%', height: 210 }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 10, right: 14, bottom: 22, left: 4 }}>
            <CartesianGrid stroke={C.grid} vertical horizontal={false} />
            <XAxis type="number" dataKey="x" stroke={C.mute} fontSize={12}
                   tickLine={false} axisLine={{ stroke: C.line }}
                   label={{ value: 'seconds on the question', position: 'insideBottom',
                            offset: -12, fill: C.mute, fontSize: 11 }} />
            <YAxis type="number" dataKey="y" domain={[-0.6, 1.6]} ticks={[0, 1]}
                   tickFormatter={(v) => (v === 1 ? 'correct' : 'missed')}
                   stroke={C.mute} fontSize={12} tickLine={false} axisLine={false}
                   width={58} />
            <ZAxis range={[38, 38]} />
            <ReferenceLine x={timing.median} stroke={C.accent} strokeDasharray="5 4"
                           label={{ value: `your median ${Math.round(timing.median)}s`,
                                    fill: C.accent, fontSize: 11, position: 'top' }} />
            <Tooltip
              cursor={{ stroke: C.line }}
              contentStyle={{ background: C.raised, border: `1px solid ${C.line}`,
                              borderRadius: 8, fontSize: 12.5 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null
                const p = (payload[0].payload as { point: TimingPoint }).point
                return (
                  <div className="chart-tip">
                    <b>D{p.domain} · {Math.round(p.seconds)}s</b>
                    <div className="s">{p.topic}</div>
                    <div className="s" style={{ color: p.correct ? C.good : C.bad }}>
                      {p.correct ? 'correct' : 'missed'}
                      {p.fast ? ' · faster than your median' : ' · slower than your median'}
                    </div>
                  </div>
                )
              }} />
            <Scatter data={missed} isAnimationActive={false}
                     fill={C.bad} fillOpacity={0.8} />
            <Scatter data={correct} isAnimationActive={false}
                     fill={C.good} fillOpacity={0.55} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      <div className="timing-cells">
        <BarRow label="Faster than your median"
                sub={`${timing.fast.n} questions · median ${Math.round(timing.fast.median_seconds ?? 0)}s`}
                stat={intervalOf(timing.fast.correct, timing.fast.n)}
                right={`${timing.fast.correct}/${timing.fast.n}`} />
        <BarRow label="Slower than your median"
                sub={`${timing.slow.n} questions · median ${Math.round(timing.slow.median_seconds ?? 0)}s`}
                stat={intervalOf(timing.slow.correct, timing.slow.n)}
                right={`${timing.slow.correct}/${timing.slow.n}`} />
      </div>

      {verdict ? (
        <p className="timing-verdict">{verdict}</p>
      ) : (
        <p className="chart-note">
          Too few questions on one side of the median to compare the two
          halves — {timing.min_per_half} each is the least that says anything.
        </p>
      )}

      {timing.enough && timing.gap.gap != null ? (
        <p className="chart-note">
          Difference: {(timing.gap.gap * 100).toFixed(0)} points, 95% CI{' '}
          {((timing.gap.low ?? 0) * 100).toFixed(0)} to {((timing.gap.high ?? 0) * 100).toFixed(0)}.
          {timing.gap.spans_zero
            ? ' That interval crosses zero, so this sitting does not establish a difference at all.'
            : ' That interval excludes zero.'}
        </p>
      ) : null}

      {timing.unanswered || timing.untimed ? (
        <p className="chart-note">
          {timing.unanswered
            ? `${timing.unanswered} unanswered, held out of the comparison — running out of time is a different problem from rushing. `
            : ''}
          {timing.untimed ? `${timing.untimed} carried no recorded time.` : ''}
        </p>
      ) : null}
    </div>
  )
}

export function Rushed({ rows }: { rows: Timing['rushed'] }) {
  if (!rows.length) return null
  return (
    <div className="list">
      {rows.map((r) => (
        <div className="list-row" key={r.id}>
          <span className="chip" style={{ borderColor: domainHue(r.domain) }}>
            D{r.domain}
          </span>
          <div className="grow">
            <div className="t">{r.topic}</div>
            <div className="s mono">{r.id}</div>
          </div>
          <div className="right">
            <div className="t" style={{ color: 'var(--bad)' }}>{Math.round(r.seconds)}s</div>
          </div>
        </div>
      ))}
    </div>
  )
}
