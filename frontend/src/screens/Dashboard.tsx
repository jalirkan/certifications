/**
 * Dashboard — where you stand and what to work on next.
 *
 * Deliberately not a progress screen. There are no streaks, no XP, no badges
 * and no "you're on fire" copy: those measure engagement, not learning. Every
 * figure here is an accuracy with its interval, and the calls to action point
 * at the weakest evidence rather than at whatever keeps you clicking.
 */

import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import { AccuracyOverTime } from '../charts/AccuracyOverTime'
import { DomainAccuracyChart } from '../charts/DomainAccuracyChart'
import { useAsync } from '../lib/hooks'
import {
  claim, hasEvidence, hms, intervalOf, MIN_CLAIM, pct, plural, rangeText, stamp,
} from '../lib/format'
import {
  BarRow, Callout, Card, Empty, ErrorNote, Loading, Section, Stat,
} from '../ui/primitives'
import { Link } from 'react-router-dom'

export function Dashboard() {
  const { epoch } = useApp()
  const nav = useNavigate()
  const overview = useAsync(() => api.overview(), [epoch])
  const trend = useAsync(() => api.trend(90, 7), [epoch])

  if (overview.loading) return <div className="wrap"><Loading /></div>
  if (overview.error || !overview.data) {
    return (
      <div className="wrap">
        <ErrorNote message={overview.error ?? 'No data'} onRetry={overview.reload} />
      </div>
    )
  }

  const o = overview.data
  // The API reports overall accuracy without bounds; it does not get to skip them.
  const overall = intervalOf(o.correct, o.attempts)
  const domainsWithData = o.domains.filter((d) => d.attempts > 0).length
  const started = o.attempts > 0
  const weakRules = o.rules.filter((r) => r.attempts >= 4).slice(0, 5)
  const weakTopics = o.topics.filter((t) => t.attempts >= 3).slice(0, 6)

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Dashboard</h1>
        <p>
          {started
            ? 'Where you stand, and what to work on next.'
            : 'Nothing logged yet. Run a drill and the diagnostics below start working.'}
        </p>
      </div>

      <div className="grid c4">
        <Stat
          label="Questions answered"
          value={o.attempts}
          foot={`${o.study_days} study ${plural(o.study_days, 'day')}`}
        />
        <Stat
          label="Overall accuracy"
          value={o.attempts ? claim(overall) : '—'}
          range={o.attempts ? `95% CI ${rangeText(overall.low, overall.high)}` : undefined}
          foot={
            /* A percentage off two answers is noise; report the count instead. */
            hasEvidence(o.last7_attempts)
              ? `${pct(o.last7)} across ${o.last7_attempts} in the last 7 days`
              : o.last7_attempts
                ? `${o.last7_attempts} answered in the last 7 days`
                : 'no activity in the last 7 days'
          }
        />
        <Stat
          label="Bank coverage"
          value={<>{o.coverage_seen}<small>/{o.coverage_total}</small></>}
          foot="questions seen at least once"
        />
        <Stat
          label="Weighted accuracy"
          /*
           * Deliberately withheld on thin evidence. It is a weighted mean of
           * domain accuracies, so it has no single Wilson interval to carry —
           * which means the only honest way to show it is to not show it until
           * the domains underneath it mean something. One lucky answer in D5
           * must never surface here as "100%".
           */
          value={
            o.weighted_accuracy == null || !hasEvidence(o.attempts)
              ? '—'
              : pct(o.weighted_accuracy)
          }
          foot={
            hasEvidence(o.attempts)
              ? `by exam weight, across ${domainsWithData} of 5 domains — not a predicted score`
              : `needs at least ${MIN_CLAIM} answers`
          }
        />
      </div>

      <Section hint="bar width is share of the exam; whisker is the 95% interval">
        By domain
      </Section>
      <Card>
        <DomainAccuracyChart domains={o.domains} />
      </Card>

      <Section hint={`${trend.data?.total_attempts ?? 0} answers on the clock`}>
        Accuracy over time
      </Section>
      <Card>
        {trend.loading ? (
          <Loading what="Loading history…" />
        ) : trend.error || !trend.data ? (
          <ErrorNote message={trend.error ?? 'No data'} onRetry={trend.reload} />
        ) : (
          <AccuracyOverTime trend={trend.data} />
        )}
      </Card>

      <div className="grid c2" style={{ marginTop: 14 }}>
        <Card>
          <h3>Weakest decision rules</h3>
          <p className="sub">
            Reasoning habits, not topics. These cost marks across every domain.
          </p>
          {weakRules.length ? (
            weakRules.map((r) => (
              <BarRow
                key={r.id}
                label={r.name}
                sub={`${r.attempts} answered`}
                stat={r}
              />
            ))
          ) : (
            <Empty>Answer about 20 questions to populate this.</Empty>
          )}
          {weakRules.length ? (
            <div className="btn-row" style={{ marginTop: 14 }}>
              <Link className="btn" to="/rules">Full diagnostic</Link>
              <button
                className="btn primary"
                onClick={() => nav('/drill/run', { state: { mode: 'costumes', n: 5 } })}
              >
                Drill the weakest rule
              </button>
            </div>
          ) : null}
        </Card>

        <Card>
          <h3>Weakest topics</h3>
          <p className="sub">
            Ranked by the lower bound, so under-tested topics surface alongside genuinely weak ones.
          </p>
          {weakTopics.length ? (
            weakTopics.map((t) => (
              <BarRow
                key={t.label}
                label={t.label}
                sub={`${t.attempts} answered`}
                stat={t}
              />
            ))
          ) : (
            <Empty>Not enough data yet.</Empty>
          )}
        </Card>
      </div>

      {started && o.attempts < MIN_CLAIM * 4 ? (
        <div style={{ marginTop: 14 }}>
          <Callout kind="info">
            <p>
              <b>Early days.</b> With {o.attempts} {plural(o.attempts, 'answer')} logged, most of
              the intervals above are still wide enough that the rankings can reshuffle. Treat them
              as "where to look", not "what is true".
            </p>
          </Callout>
        </div>
      ) : null}

      <Section>Quick start</Section>
      <div className="btn-row">
        <button
          className="btn primary"
          onClick={() => nav('/drill/run', { state: { mode: 'smart', n: 20 } })}
        >
          Drill 20 questions
        </button>
        <button
          className="btn"
          onClick={() => nav('/drill/run', { state: { mode: 'due', n: 20 } })}
        >
          What I'm about to forget
        </button>
        <button
          className="btn"
          onClick={() => nav('/drill/run', { state: { mode: 'principle', n: 15 } })}
        >
          Target weak rules
        </button>
        <Link className="btn" to="/exam">Mock exam</Link>
        <Link className="btn" to="/cases">Branching case</Link>
        <Link className="btn" to="/games">Short form</Link>
      </div>

      {o.exams.length ? (
        <>
          <Section>Recent exams</Section>
          <Card>
            <div className="list">
              {o.exams.map((e) => (
                <div className="list-row" key={e.id}>
                  <div className="grow">
                    <div className="t">
                      {e.submitted ? 'Submitted' : 'In progress'} ·{' '}
                      <span className="mono">{e.id}</span>
                    </div>
                    <div className="s">
                      {stamp(e.created)} · {e.answered}/{e.total} answered · {hms(e.elapsed)} used
                    </div>
                  </div>
                  <Link
                    className="btn"
                    to={`/exam/${e.submitted ? 'result' : 'run'}/${e.id}`}
                  >
                    {e.submitted ? 'Review' : 'Resume'}
                  </Link>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : null}

      {o.games ? (
        <p className="chart-note" style={{ marginTop: 18 }}>
          {o.games} short-form {plural(o.games, 'result')} logged separately, and deliberately kept
          out of every figure on this page. <Link to="/games">See them</Link>.
        </p>
      ) : null}
    </div>
  )
}
