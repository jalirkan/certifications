/**
 * Detection — does this tool actually work?
 *
 * Every other screen reports on the learner. This one reports on the
 * instrument: each diagnostic was run against synthetic learners whose
 * weaknesses were planted deliberately, so the right answer was known before
 * anyone looked.
 *
 * **The failures lead.** Two diagnostics do not hold up, and they are the most
 * interesting thing here — a tool that publishes evidence against itself is
 * worth more than one that publishes a wall of green. If this screen ever
 * reads as reassuring, it has been built wrong.
 *
 * Nothing here is computed on load. A full sweep is roughly fifteen minutes of
 * CPU; the screen reads a persisted result and says so, including the date, so
 * a stale report cannot pass for a fresh one.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip,
  XAxis, YAxis,
} from 'recharts'
import { api } from '../api/client'
import type {
  Detection, DetectionCell, DetectionCheck, DetectionReport,
} from '../api/types'
import { C } from '../charts/theme'
import { plural, stamp } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { Callout, Card, ErrorNote, Loading, Section, Stat } from '../ui/primitives'

const pct = (v: number | null | undefined) =>
  v == null ? '—' : `${Math.round(v * 100)}%`

const band = (r: { low: number | null; high: number | null }) =>
  r.low == null || r.high == null
    ? '—'
    : `${Math.round(r.low * 100)}–${Math.round(r.high * 100)}%`

/** The largest sample size swept, where a claim is at its strongest. */
function biggest(check: DetectionCheck): DetectionCell | null {
  return check.cells.length ? check.cells[check.cells.length - 1] : null
}

type Thresholds = { detection_floor: number; false_positive_ceiling: number }

/**
 * Why a check failed, distinguishing three different problems.
 *
 * A check can fail by missing what was planted, by firing on learners with
 * nothing wrong, or simply by not having been run enough times to tell either
 * way. Judging on the interval alone conflates the last with the second: at a
 * dozen runs a 5% false-positive rate still has an upper bound past 30%, and
 * labelling that "fires on everybody" would be a false accusation against a
 * diagnostic that is probably fine.
 *
 * So the label follows the point estimate, and the interval decides only
 * whether the claim is strong enough to call trustworthy.
 */
function verdictOf(check: DetectionCheck, t: Thresholds): {
  ok: boolean
  reason: 'trustworthy' | 'indiscriminate' | 'blind' | 'thin'
} {
  const cell = biggest(check)
  if (!cell) return { ok: false, reason: 'thin' }
  if (check.trustworthy_from != null) return { ok: true, reason: 'trustworthy' }

  const fp = cell.false_positive.rate
  const det = cell.detection.rate
  if (fp != null && fp > t.false_positive_ceiling) {
    return { ok: false, reason: 'indiscriminate' }
  }
  if (det != null && det < t.detection_floor) return { ok: false, reason: 'blind' }
  // Rates are fine; the intervals are simply too wide to claim anything.
  return { ok: false, reason: 'thin' }
}

const REASON_LABEL: Record<string, string> = {
  trustworthy: 'holds up',
  indiscriminate: 'fires on learners with nothing wrong',
  blind: 'misses what was planted',
  thin: 'too few runs to tell',
}

/** Detection against false positives, across sample size. */
function CheckCurve({ check, thresholds }: {
  check: DetectionCheck; thresholds: Thresholds
}) {
  const data = check.cells.map((c) => ({
    attempts: c.attempts,
    detection: c.detection.rate,
    falsePositive: c.false_positive.rate,
  }))
  if (data.length < 2) return null

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={170}>
        <LineChart data={data} margin={{ top: 8, right: 14, bottom: 4, left: -20 }}>
          <CartesianGrid stroke={C.grid} vertical={false} />
          <XAxis dataKey="attempts" tick={{ fill: C.mute, fontSize: 11 }}
                 stroke={C.line} />
          <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]}
                 tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                 tick={{ fill: C.mute, fontSize: 11 }} stroke={C.line} />
          <ReferenceLine y={thresholds.detection_floor} stroke={C.mute}
                         strokeDasharray="3 3" />
          <ReferenceLine y={thresholds.false_positive_ceiling} stroke={C.mute}
                         strokeDasharray="3 3" />
          <Tooltip
            contentStyle={{ background: C.raised, border: `1px solid ${C.line}`,
                            borderRadius: 8, fontSize: 12.5 }}
            labelFormatter={(v) => `${v} answers`}
            formatter={(v, name) =>
              [pct(typeof v === 'number' ? v : null),
               name === 'detection' ? 'detected' : 'false positive'] as [string, string]}
          />
          <Line dataKey="detection" stroke={C.good} strokeWidth={2} dot
                isAnimationActive={false} name="detection" />
          <Line dataKey="falsePositive" stroke={C.bad} strokeWidth={2} dot
                isAnimationActive={false} name="falsePositive" />
        </LineChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Green is detection, red is false positives. The dashed lines are the bar:
        detection above {pct(thresholds.detection_floor)}, false positives below{' '}
        {pct(thresholds.false_positive_ceiling)}. A check is only useful where the
        green line is high <em>and</em> the red one is low.
      </p>
    </div>
  )
}

function CellTable({ check, ceiling }: { check: DetectionCheck; ceiling: number }) {
  return (
    <div className="detect-table">
      <div className="detect-row detect-head">
        <span>Answers</span><span>Detected</span><span>95% CI</span>
        <span>False positive</span><span>95% CI</span><span></span>
      </div>
      {check.cells.map((c) => (
        <div className="detect-row" key={c.attempts}>
          <span className="mono">{c.attempts}</span>
          <span>{pct(c.detection.rate)}</span>
          <span className="dim mono">{band(c.detection)}</span>
          <span className={c.false_positive.rate != null
            && c.false_positive.rate > ceiling ? 'bad-text' : ''}>
            {pct(c.false_positive.rate)}</span>
          <span className="dim mono">{band(c.false_positive)}</span>
          <span>{c.trustworthy ? <span className="chip good">holds</span> : null}</span>
        </div>
      ))}
    </div>
  )
}

function CheckCard({ check, open, thresholds }: {
  check: DetectionCheck; open: boolean; thresholds: Thresholds
}) {
  const [expanded, setExpanded] = useState(open)
  const verdict = verdictOf(check, thresholds)
  const cell = biggest(check)

  return (
    <Card className={`detect-card ${verdict.ok ? '' : 'failing'}`.trim()}>
      <div className="detect-card-head">
        <div className="grow">
          <h3>
            <span className="mono dim">{check.id}</span> {check.title}
          </h3>
          <div className="s">
            <code className="mono">{check.diagnostic}</code>
          </div>
        </div>
        <div className="right">
          <span className={`chip ${verdict.ok ? 'good' : 'bad'}`}>
            {REASON_LABEL[verdict.reason]}
          </span>
          <div className="s" style={{ marginTop: 5 }}>
            {check.trustworthy_from != null
              ? `from ${check.trustworthy_from} answers`
              : 'not at any size swept'}
          </div>
        </div>
      </div>

      <p className="detect-planted">
        <span className="kicker">Planted</span> {check.planted}
      </p>

      {cell ? (
        <p className="sub" style={{ margin: '0 0 12px' }}>
          At {cell.attempts} answers: detected <b>{pct(cell.detection.rate)}</b>{' '}
          <span className="dim">({band(cell.detection)})</span>, fired on{' '}
          <b className={cell.false_positive.rate != null
            && cell.false_positive.rate > thresholds.false_positive_ceiling
            ? 'bad-text' : ''}>{pct(cell.false_positive.rate)}</b>{' '}
          <span className="dim">({band(cell.false_positive)})</span> of learners
          with nothing planted.
        </p>
      ) : null}

      <button className="btn ghost" onClick={() => setExpanded((v) => !v)}>
        {expanded ? 'Hide the numbers' : 'Show the numbers'}
      </button>

      {expanded ? (
        <div style={{ marginTop: 14 }}>
          <CellTable check={check}
                     ceiling={thresholds.false_positive_ceiling} />
          <CheckCurve check={check} thresholds={thresholds} />
          {check.note ? <p className="sub">{check.note}</p> : null}
        </div>
      ) : null}
    </Card>
  )
}

export function DetectionScreen() {
  const state = useAsync<Detection>(() => api.detection(), [])

  if (state.loading) return <div className="wrap"><Loading /></div>
  if (state.error || !state.data) {
    return (
      <div className="wrap">
        <ErrorNote message={state.error ?? 'No data'} onRetry={state.reload} />
      </div>
    )
  }

  if (!state.data.available) {
    return (
      <div className="wrap narrow">
        <div className="page-head">
          <h1>Detection</h1>
          <p>Whether the diagnostics in this tool actually find what they claim to.</p>
        </div>
        <Callout kind="info">
          <p><b>Nothing has been measured yet.</b> {state.data.reason}</p>
          <p>
            Run this from the repository root — it takes about fifteen minutes:
          </p>
          <p><code className="mono">{state.data.command}</code></p>
        </Callout>
      </div>
    )
  }

  const report: DetectionReport = state.data
  const headline = report.checks.filter((c) => !c.component)
  const t = report.thresholds
  const failing = headline.filter((c) => !verdictOf(c, t).ok)
  const holding = headline.filter((c) => verdictOf(c, t).ok)
  const components = report.checks.filter((c) => c.component)

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Detection</h1>
        <p>
          Every other screen reports on you. This one reports on the tool. Each
          diagnostic was run against synthetic learners whose weaknesses were
          planted deliberately, so the right answer was known before anyone
          looked — and each was run again against learners with nothing wrong,
          because a check that fires on everybody detects everything and tells
          you nothing.
        </p>
      </div>

      <div className="grid c4">
        <Stat label="Checks that hold up" value={`${holding.length}/${headline.length}`}
              foot="detection high, false positives low" />
        <Stat label="Checks that do not" value={failing.length}
              foot="listed first, below" />
        <Stat label="Runs per cell" value={report.seeds}
              foot="a single seed is a coin flip" />
        <Stat label="Bank measured against" value={report.bank.questions}
              foot={`${report.bank.rules} decision rules`} />
      </div>

      <div style={{ marginTop: 16 }}>
        <Callout kind="info">
          <p>
            Measured {stamp(report.generated)} · {report.seeds} runs per cell ·
            sample sizes {report.sizes.join(', ')} · rates carry 95% Wilson
            intervals. Nothing on this page is recomputed when you open it.
          </p>
        </Callout>
      </div>

      {/* The failures lead. They are the reason this screen is worth having. */}
      {failing.length ? (
        <>
          <Section hint="the most useful thing on this page">
            What does not hold up
          </Section>
          {failing.map((c) => (
            <CheckCard key={c.id} check={c} open thresholds={t} />
          ))}
        </>
      ) : null}

      <Section>What the sweep says</Section>
      <Card>
        {report.findings.map((line, i) => (
          <p key={i} className="finding"
             dangerouslySetInnerHTML={{ __html: markdownish(line) }} />
        ))}
      </Card>

      {holding.length ? (
        <>
          <Section hint="detection high, false positives low">
            What holds up
          </Section>
          {holding.map((c) => (
            <CheckCard key={c.id} check={c} open={false} thresholds={t} />
          ))}
        </>
      ) : null}

      {components.length ? (
        <>
          <Section hint="reported separately because the halves fail differently">
            Components
          </Section>
          {components.map((c) => (
            <CheckCard key={c.id} check={c} open={false} thresholds={t} />
          ))}
        </>
      ) : null}

      {report.measures.some((m) => m.points.length) ? (
        <>
          <Section>Measured, not scored</Section>
          <Card>
            {report.measures.filter((m) => m.points.length).map((m) => (
              <div key={m.name}>
                <p className="sub" style={{ marginBottom: 8 }}>{m.label}</p>
                <div className="list">
                  {m.points.map((p) => (
                    <div className="list-row" key={p.attempts}>
                      <div className="grow">
                        <div className="t">{p.attempts} answers</div>
                        <div className="s">{p.runs} {plural(p.runs, 'run')}</div>
                      </div>
                      <span className="chip mono">{pct(p.mean)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </Card>
        </>
      ) : null}

      <div className="btn-row" style={{ marginTop: 20 }}>
        <Link className="btn" to="/rules">The decision-rule diagnostic</Link>
        <Link className="btn" to="/bank">Item analysis</Link>
      </div>
    </div>
  )
}

/**
 * The findings arrive as markdown-ish prose generated from the numbers.
 * Only bold and italic are honoured, and everything else is escaped — the text
 * is generated locally rather than user-supplied, but escaping first costs
 * nothing and means this stays safe if that ever changes.
 */
function markdownish(text: string): string {
  const escaped = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return escaped
    .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
}
