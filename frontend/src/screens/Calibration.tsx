/**
 * Calibration — did you know that you knew?
 *
 * The dangerous quadrant leads the page on purpose. Confident-and-wrong is the
 * only cell nothing else in this system surfaces: those questions are answered,
 * logged, and to every other report they look like ordinary misses. They are
 * the ones that sink people, because they read as wins.
 *
 * There is no "calibration score" here and there should not be one. The curve,
 * the gap and the lists are the output; collapsing them to a single number
 * throws away the part that tells you what to do.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar, BarChart, Cell, CartesianGrid, ErrorBar, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import type {
  Calibration as CalibrationData, CalibrationBucket, CalibrationCell,
  CalibrationItem, Projection,
} from '../api/types'
import { C } from '../charts/theme'
import { pct, plural, rangeText, stamp } from '../lib/format'
import { useAsync } from '../lib/hooks'
import {
  Callout, Card, Empty, ErrorNote, Loading, Section, Stat,
} from '../ui/primitives'

const LEVEL_HUE: Record<string, string> = {
  guess: C.mute,
  unsure: C.warn,
  confident: C.accent,
}

function CurveTip({ active, payload }: {
  active?: boolean
  payload?: { payload: CalibrationCell }[]
}) {
  if (!active || !payload?.length) return null
  const c = payload[0].payload
  return (
    <div className="tip">
      <div className="t">{c.level}</div>
      <div className="r">
        {c.accuracy == null ? 'no data' : `${pct(c.accuracy)} · 95% CI ${rangeText(c.low, c.high)}`}
      </div>
      <div className="s">
        {c.correct}/{c.attempts} correct{c.enough ? '' : ' — too few to call'}
      </div>
    </div>
  )
}

/**
 * The curve, with an interval on every bar.
 *
 * Rising is well calibrated. The interesting failure is flat: it means
 * confidence carries no information about correctness, which is worse than
 * being uniformly overconfident because there is nothing to correct for.
 */
function CalibrationCurve({ curve }: { curve: CalibrationCell[] }) {
  const data = curve.map((c) => ({
    ...c,
    value: c.accuracy ?? 0,
    err: [
      Math.max(0, (c.accuracy ?? 0) - (c.low ?? 0)),
      Math.max(0, (c.high ?? 0) - (c.accuracy ?? 0)),
    ] as [number, number],
  }))
  if (!curve.some((c) => c.attempts)) {
    return (
      <p className="chart-note">
        No answers carry a confidence rating yet. Run a drill — confidence is taken
        with the answer, so it cannot be filled in later.
      </p>
    )
  }

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={data} margin={{ top: 10, right: 14, bottom: 4, left: -18 }}>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="level" tick={{ fill: C.dim, fontSize: 12 }} stroke={C.line} />
          <YAxis
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
            tick={{ fill: C.mute, fontSize: 11 }}
            stroke={C.line}
          />
          <Tooltip content={<CurveTip />} cursor={{ fill: 'rgba(255,255,255,.03)' }} />
          <Bar dataKey="value" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell
                key={d.level}
                fill={LEVEL_HUE[d.level] ?? C.accent}
                fillOpacity={d.enough ? 0.85 : 0.3}
              />
            ))}
            <ErrorBar dataKey="err" width={5} strokeWidth={1.3} stroke={C.text} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Rising left to right means your confidence is telling you something. A flat line
        means it is not. Faded bars have too few answers to read as anything yet.
      </p>
    </div>
  )
}

function ItemList({ items, empty }: { items: CalibrationItem[]; empty: string }) {
  if (!items.length) return <Empty>{empty}</Empty>
  return (
    <div className="list">
      {items.map((item) => (
        <div className="list-row" key={`${item.question_id}-${item.ts}`}>
          <span className="mono">{item.question_id}</span>
          <div className="grow">
            <div className="t">{item.topic}</div>
            <div className="s">
              {stamp(item.ts)}
              {item.rule ? ` · rule: ${item.rule}` : ''}
              {item.chosen ? ` · you chose ${item.chosen}` : ''}
              {item.answer ? `, answer ${item.answer}` : ''}
            </div>
          </div>
          <span className="chip">{item.confidence}</span>
        </div>
      ))}
    </div>
  )
}

function BucketRows({ buckets, kind }: {
  buckets: CalibrationBucket[]
  kind: 'dangerous' | 'lucky'
}) {
  const rows = buckets.filter((b) => b[kind] > 0).slice(0, 10)
  if (!rows.length) {
    return <Empty>Nothing to show on this axis yet.</Empty>
  }
  return (
    <div className="list">
      {rows.map((b) => (
        <div className="list-row" key={b.key}>
          <div className="grow">
            <div className="t">{b.label}</div>
            <div className="s">
              {b.confident_attempts
                ? `${b.confident_accuracy == null ? '—' : pct(b.confident_accuracy)} of ${b.confident_attempts} confident answers · 95% CI ${rangeText(b.confident_low, b.confident_high)}`
                : `${b.attempts} rated`}
              {b.enough ? '' : ' · too few to call'}
            </div>
          </div>
          <span className={`chip ${kind === 'dangerous' ? 'bad' : ''}`.trim()}>
            {b[kind]}
          </span>
        </div>
      ))}
    </div>
  )
}

function Horizon({ projection, onSave }: {
  projection: Projection
  onSave: (value: string) => void
}) {
  const p = projection
  const [value, setValue] = useState(p.target ?? '')

  return (
    <Card>
      <div className="grid c2">
        <div>
          <div className="field">
            <label htmlFor="target">Target exam date</label>
            <div className="profile-row">
              <input
                id="target"
                type="date"
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
              <button className="btn" onClick={() => onSave(value)}>Save</button>
              {p.target ? (
                <button className="btn ghost" onClick={() => { setValue(''); onSave('') }}>
                  Clear
                </button>
              ) : null}
            </div>
          </div>
          <p className="sub" style={{ margin: 0 }}>
            Optional. Used for coverage arithmetic only.
          </p>
        </div>
        <div>
          <Stat
            label="Questions seen 5+ times"
            value={<>{p.covered}<small>/{p.questions}</small></>}
            foot={`${p.attempts_remaining} answers to cover the bank`}
          />
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        {!p.enough ? (
          <Callout kind="info">
            <p>
              <b>Not enough recent activity to project a pace.</b> {p.recent_attempts}{' '}
              {plural(p.recent_attempts, 'answer')} in the last {p.window_days} days;
              this needs about {p.min_pace_attempts} before the arithmetic says anything.
              {p.target && p.days_to_target != null
                ? ` Your target is ${p.days_to_target} days away.`
                : ''}
            </p>
          </Callout>
        ) : (
          <Callout kind={p.on_track === false ? 'warn' : 'info'}>
            <p>
              At <b>{p.pace_per_day.toFixed(1)} answers/day</b> over the last {p.window_days}{' '}
              days, every question reaches {p.coverage_target} attempts in about{' '}
              <b>{Math.round(p.days_needed ?? 0)} days</b> — around {p.projected_date}.
              {p.target && p.margin_days != null
                ? p.margin_days >= 0
                  ? ` That is ${p.margin_days} days before your ${p.target} target.`
                  : ` That is about ${Math.abs(p.margin_days)} days past your ${p.target} target.`
                : ''}
            </p>
            <p>
              Coverage arithmetic only — it says nothing about whether you will still
              remember what you covered. A retention forecast needs review history this
              tool has not collected yet.
            </p>
          </Callout>
        )}
      </div>
    </Card>
  )
}

export function CalibrationScreen() {
  const { epoch, toast } = useApp()
  const data = useAsync<CalibrationData>(() => api.calibration(), [epoch])
  const [axis, setAxis] = useState<'by_rule' | 'by_topic'>('by_rule')

  if (data.loading) return <div className="wrap"><Loading /></div>
  if (data.error || !data.data) {
    return (
      <div className="wrap">
        <ErrorNote message={data.error ?? 'No data'} onRetry={data.reload} />
      </div>
    )
  }

  const d = data.data
  const gap = d.gap

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Calibration</h1>
        <p>
          The rest of the system measures whether you were right. This measures whether you
          knew you were right — and the gap between those two is where exam failures live.
        </p>
      </div>

      {!d.labelled ? (
        <Callout kind="info">
          <p>
            <b>No answers are rated yet.</b> Confidence is captured with the answer, in one
            extra keystroke, and cannot be filled in afterwards — so this page fills up from
            here forward, not retrospectively.
          </p>
          {d.unlabelled ? (
            <p>
              {d.unlabelled} earlier {plural(d.unlabelled, 'answer')} predate the feature and
              stay unlabelled. They still count in every other report.
            </p>
          ) : null}
          <p><Link className="btn primary" to="/drill">Run a drill</Link></p>
        </Callout>
      ) : (
        <>
          {/* Leads the page: nothing else in the tool surfaces these. */}
          <Section hint="confident, and wrong">The dangerous quadrant</Section>
          <Card>
            <p className="sub">
              You were sure and you were not right. Nothing else in this system will ever
              bring these back to you — to every other report they look like ordinary misses.
            </p>
            <ItemList
              items={d.dangerous}
              empty="Nothing here. Either your confidence is well placed, or you have not rated enough answers yet."
            />
          </Card>

          <div className="grid c4" style={{ marginTop: 18 }}>
            <Stat
              label="Answers rated"
              value={d.labelled}
              foot={d.unlabelled ? `${d.unlabelled} predate the feature` : 'all of them'}
            />
            <Stat
              label="Confident and wrong"
              value={d.dangerous.length}
              foot="the quadrant that costs marks"
            />
            <Stat
              label="Right but not known"
              value={d.lucky.length}
              foot="guessed or unsure, and correct"
            />
            <Stat
              label="Overconfidence gap"
              value={
                gap.gap == null || !gap.enough
                  ? '—'
                  : `${gap.gap >= 0 ? '+' : ''}${Math.round(gap.gap * 100)} pts`
              }
              range={
                gap.gap_low != null && gap.gap_high != null
                  ? `95% CI ${gap.gap_low >= 0 ? '+' : ''}${Math.round(gap.gap_low * 100)} to ${
                      gap.gap_high >= 0 ? '+' : ''
                    }${Math.round(gap.gap_high * 100)} pts`
                  : undefined
              }
              foot={
                gap.enough
                  ? 'when confident, versus when not'
                  : `needs ${d.min_level}+ answers either side`
              }
            />
          </div>

          <Section>The curve</Section>
          <Card>
            <CalibrationCurve curve={d.curve} />
            {gap.enough && gap.spans_zero ? (
              <Callout>
                <p>
                  <b>Your confidence is not yet telling you anything.</b> Being confident is
                  worth about {Math.round(gap.gap! * 100)} points over answering unsure — but
                  the interval on that runs from {Math.round(gap.gap_low! * 100)} to{' '}
                  {Math.round(gap.gap_high! * 100)} points, which includes zero. Read that as
                  no relationship established yet rather than as a small one. Keep answering.
                </p>
              </Callout>
            ) : null}
          </Card>

          <Section hint="the more actionable axis is usually the rule">
            Where it goes wrong
          </Section>
          <Card>
            <div className="seg" style={{ marginBottom: 14 }}>
              <button className={axis === 'by_rule' ? 'on' : ''}
                      onClick={() => setAxis('by_rule')}>
                By decision rule
              </button>
              <button className={axis === 'by_topic' ? 'on' : ''}
                      onClick={() => setAxis('by_topic')}>
                By topic
              </button>
            </div>
            <p className="sub">
              {axis === 'by_rule'
                ? '"Overconfident specifically on evidence-quality questions" names the reasoning habit, which transfers to questions you have not seen.'
                : 'Useful for revision planning, but a topic is a subject, not a habit.'}
            </p>
            <BucketRows buckets={d[axis]} kind="dangerous" />
          </Card>

          <Section>Right, but not known</Section>
          <Card>
            <p className="sub">
              Guessed or unsure, and correct. Not failures — but not learned either, and
              currently indistinguishable from mastery everywhere else in the tool.
            </p>
            <ItemList items={d.lucky} empty="Nothing recorded yet." />
          </Card>
        </>
      )}

      <Section>Study horizon</Section>
      <Horizon
        projection={d.projection}
        onSave={async (value) => {
          try {
            await api.saveSettings(value)
            toast(value ? `Target set to ${value}` : 'Target cleared')
            data.reload()
          } catch (err) {
            toast(err instanceof Error ? err.message : String(err), true)
          }
        }}
      />
    </div>
  )
}
