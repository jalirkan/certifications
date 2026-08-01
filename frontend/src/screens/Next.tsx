/**
 * Next session — what to do in the next thirty minutes, and why.
 *
 * The design constraint is the whole feature: **every row states its reason in
 * one line with numbers.** "Drill evidence-quality — 28 of 89 correct, 95% CI
 * 23–42%, spans 5 domains" is a recommendation. "Recommended for you" is a
 * slot machine, and this is the one screen in the app that could quietly turn
 * into one. The evidence line is not a subtitle; it is the reason the row
 * exists, so it is rendered at the same weight as the title and never
 * truncated.
 *
 * **What was withheld is shown too**, and is not an error state. "No decision
 * rule has 4 answers yet" tells the learner precisely what to do about it,
 * where an empty screen would just look broken. On a new profile this section
 * is most of the page, which is correct.
 *
 * Nothing here predicts anything — no readiness figure, no countdown, no
 * relabelled scaled score. See CLAUDE.md §3.7. The ordering carries the
 * judgement instead: what is known wrong, then what is measured well enough
 * to rank, then what is too thinly tested to call, then ground never covered,
 * then pace as context.
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { NextSession, Recommendation } from '../api/types'
import { plural } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { Callout, Card, ErrorNote, Loading, Section } from '../ui/primitives'

const BUDGETS = [15, 30, 60, 120]

/** What each group means, in the learner's terms rather than the code's. */
const GROUP_LABEL: Record<number, string> = {
  0: 'Known wrong',
  1: 'Weakest, and measured well enough to rank',
  2: 'Too thinly tested to call',
  3: 'New ground',
  4: 'Pace',
}

/*
 * The group-1 wording is deliberately about measurement, not badness. These are
 * the weakest items whose intervals are narrow enough that the ordering means
 * something - which is not the same as saying each one is a weakness. A rule at
 * 46-75% belongs here because it is well measured, and calling that heading
 * "measured weaknesses" would overclaim on its own numbers.
 */
const GROUP_NOTE: Record<number, string> = {
  0: 'Questions you missed, answers you were sure about and got wrong, an unfinished case.',
  1: 'Enough answers behind each of these that the ordering means something.',
  2: 'Worth drilling, but the evidence cannot yet say whether it is a weakness or just untested.',
  3: 'Never served, never played. Not a deficit — just unmeasured.',
  4: 'Arithmetic over your own log. Not a forecast.',
}

const KIND_ICON: Record<string, string> = {
  due: 'M3 12a9 9 0 109-9v4',
  dangerous: 'M12 3a9 9 0 100 18 9 9 0 000-18zm0 4v6m0 3v.01',
  rule: 'M12 3a9 9 0 100 18 9 9 0 000-18zM15.5 8.5l-2 5-5 2 2-5 5-2z',
  topic: 'M12 3l9 5-9 5-9-5 9-5zM3 13l9 5 9-5',
  unseen: 'M12 5v14M5 12h14',
  case: 'M6 3v6a3 3 0 003 3h6a3 3 0 013 3v6',
  coverage: 'M3 20h18M6 20V10m6 10V5m6 15v-7',
}

function Icon({ kind }: { kind: string }) {
  return (
    <svg className="rec-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={KIND_ICON[kind] ?? KIND_ICON.topic} />
    </svg>
  )
}

/** Where a row sends you. Built from the action the engine chose, not guessed. */
function hrefFor(rec: Recommendation): string {
  const a = rec.action
  if (a.screen === 'calibration') return '#/calibration'
  if (a.screen === 'case') {
    if (a.session) return `#/cases/run/${a.session}`
    // Named in the title, so land on that case rather than the bare list.
    return a.case_id ? `#/cases?case=${encodeURIComponent(a.case_id)}` : '#/cases'
  }
  const q = new URLSearchParams()
  if (a.mode) q.set('mode', a.mode)
  if (a.principle) q.set('principle', a.principle)
  if (a.topic) q.set('topic', a.topic)
  if (a.n) q.set('n', String(a.n))
  const query = q.toString()
  return query ? `#/drill?${query}` : '#/drill'
}

function Row({ rec }: { rec: Recommendation }) {
  return (
    <a className={`rec rec-${rec.basis}`} href={hrefFor(rec)}>
      <Icon kind={rec.kind} />
      <div className="rec-body">
        <div className="rec-title">{rec.title}</div>
        {/* The reason the row exists. Never truncated, never de-emphasised. */}
        <div className="rec-evidence">{rec.evidence}</div>
      </div>
      <div className="rec-minutes">
        <b>{rec.minutes}</b>
        <span>min</span>
      </div>
    </a>
  )
}

function Grouped({ rows }: { rows: Recommendation[] }) {
  const groups = [...new Set(rows.map((r) => r.group))].sort((a, b) => a - b)
  return (
    <>
      {groups.map((g) => (
        <div className="rec-group" key={g}>
          <div className="rec-group-head">
            <h3>{GROUP_LABEL[g] ?? 'Other'}</h3>
            <p>{GROUP_NOTE[g]}</p>
          </div>
          {rows.filter((r) => r.group === g).map((r, i) => (
            <Row key={`${r.kind}-${i}`} rec={r} />
          ))}
        </div>
      ))}
    </>
  )
}

export function NextScreen() {
  const [minutes, setMinutes] = useState(30)
  const navigate = useNavigate()
  const state = useAsync<NextSession>(() => api.nextSession(minutes), [minutes])

  if (state.loading) return <Loading what="Working out what is worth doing…" />
  if (state.error) return <ErrorNote message={state.error} onRetry={state.reload} />
  const data = state.data
  if (!data) return null

  const spent = data.recommendations.reduce((s, r) => s + r.minutes, 0)

  return (
    <>
      <Section hint="Assembled from your own answer log. Every line states the numbers behind it.">
        <h1>Next session</h1>
      </Section>

      <Card className="next-head">
        <div className="budget" role="group" aria-label="Time budget">
          {BUDGETS.map((m) => (
            <button key={m} type="button"
                    className={m === minutes ? 'on' : ''}
                    aria-pressed={m === minutes}
                    onClick={() => setMinutes(m)}>
              {m} min
            </button>
          ))}
        </div>
        <p className="pace">
          {data.pace.measured ? (
            <>
              Timings use your median of <b>{Math.round(data.pace.seconds)}s</b> a
              question, over {data.pace.n} answers.
            </>
          ) : (
            <>
              Timings assume <b>{Math.round(data.pace.seconds)}s</b> a question — you
              have {data.pace.n} timed {plural(data.pace.n, 'answer')}, too few to
              measure your own pace.
            </>
          )}
        </p>
      </Card>

      {data.recommendations.length ? (
        <>
          <Section hint={`${spent} of ${data.minutes} minutes planned`}>
            <h2>The plan</h2>
          </Section>
          <Grouped rows={data.recommendations} />
        </>
      ) : (
        <Callout>
          <b>Nothing has enough evidence behind it yet.</b> Rather than invent a
          recommendation, this screen says so. The reasons are below — most of
          them resolve after one drill.
        </Callout>
      )}

      {data.also.length ? (
        <>
          <Section hint={`Outside the ${data.minutes} minutes, in the order they would be picked up`}>
            <h2>Also worth doing</h2>
          </Section>
          <Grouped rows={data.also} />
        </>
      ) : null}

      {data.withheld.length ? (
        <>
          <Section hint="Not an error. This is what the log cannot yet support, and what would fix it.">
            <h2>Not recommended, and why</h2>
          </Section>
          <Card>
            <ul className="withheld">
              {data.withheld.map((w, i) => (
                <li key={i}>
                  <span className="chip dim">{w.kind}</span>
                  {w.reason}
                </li>
              ))}
            </ul>
          </Card>
        </>
      ) : null}

      <Card className="next-foot">
        <button type="button" className="btn" onClick={() => navigate('/drill')}>
          Set up a drill yourself
        </button>
        <p>
          None of this is a prediction. It is an ordering of what your own answer
          log can currently support, most-evidenced first.
        </p>
      </Card>
    </>
  )
}
