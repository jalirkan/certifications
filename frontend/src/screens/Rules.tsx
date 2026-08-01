/**
 * Decision rules — the diagnostic axis that transfers.
 *
 * Topics answer "what should I study". Rules answer "which reasoning habit is
 * costing me marks across every domain", which is the only axis here that
 * applies to questions that do not exist yet — the actual exam condition.
 *
 * Rules are never forced onto questions to raise coverage, so a rule with no
 * evidence is shown as untested rather than quietly ranked.
 */

import { useNavigate, Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import { RuleDotPlot } from '../charts/RuleDotPlot'
import { useAsync } from '../lib/hooks'
import { hasEvidence, pct, rangeText } from '../lib/format'
import { Callout, Card, ErrorNote, Loading, Section } from '../ui/primitives'

export function Rules() {
  const { epoch, toast } = useApp()
  const nav = useNavigate()
  const overview = useAsync(() => api.overview(), [epoch])

  if (overview.loading) return <div className="wrap"><Loading /></div>
  if (overview.error || !overview.data) {
    return (
      <div className="wrap">
        <ErrorNote message={overview.error ?? 'No data'} onRetry={overview.reload} />
      </div>
    )
  }

  const rules = overview.data.rules
  const tested = rules.filter((r) => r.attempts >= 4)
  const thin = rules.filter((r) => r.attempts < 4)
  /*
   * A point estimate under 80% is not evidence of a problem - with six attempts
   * it is mostly noise. Requiring the whole 95% interval to sit below target
   * means "you are weak on this" is a claim the data actually supports, at the
   * cost of surfacing fewer rules early on. That trade is the right way round:
   * a false weakness sends you drilling the wrong thing.
   */
  const actionable = tested
    .filter((r) => hasEvidence(r.attempts) && (r.high ?? 1) < 0.8)
    .slice(0, 3)

  const drillRule = (principle?: string) => {
    nav('/drill/run', { state: { mode: 'costumes', principle } })
    if (!principle) toast('Targeting your weakest rule')
  }

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Decision rules</h1>
        <p>
          A different question from the dashboard. Not which topics you are weak on, but which
          reasoning habits are costing you marks across all of them — the only axis here that
          transfers to questions that do not exist yet.
        </p>
      </div>

      <div className="btn-row" style={{ marginBottom: 20 }}>
        <Link className="btn" to="/rules/card">Study card</Link>
        {/* This axis makes a claim. Link to the evidence for it, including
            the half of that claim which did not survive testing. */}
        <Link className="btn" to="/detection">Does this axis work?</Link>
        <button className="btn primary" onClick={() => drillRule()} disabled={!tested.length}>
          Drill the weakest rule
        </button>
      </div>

      <Section hint="ranked weakest first; the bar is the 95% interval">Diagnostic</Section>
      <Card>
        <RuleDotPlot rules={rules} />
      </Card>

      {actionable.length ? (
        <>
          <Section>What to actually fix</Section>
          {actionable.map((r) => (
            <Card key={r.id}>
              <h3>
                {r.name}{' '}
                <span className="chip bad" style={{ marginLeft: 6 }}>{pct(r.accuracy)}</span>
                <span className="chip" style={{ marginLeft: 6 }}>
                  95% CI {rangeText(r.low, r.high)}
                </span>
              </h3>
              <p className="sub" style={{ marginBottom: 4 }}>You are likely doing this instead</p>
              <p style={{ fontSize: 13.5, color: 'var(--text-dim)', margin: '0 0 12px' }}>
                {r.misapplication}
              </p>
              <p className="sub" style={{ margin: 0 }}>Watch the boundary</p>
              <p style={{ fontSize: 13.5, color: 'var(--text-dim)', margin: '0 0 14px' }}>
                {r.scope}
              </p>
              <button className="btn" onClick={() => drillRule(r.id)}>
                Drill this rule across every domain
              </button>
            </Card>
          ))}
        </>
      ) : tested.length ? (
        <div style={{ marginTop: 14 }}>
          <Callout kind="info">
            <p>
              No rule is confidently below 80% yet. Some of the ranked rules above have lower
              point estimates, but their intervals still reach past the target — which means the
              gap could be sampling noise. Keep drilling and check back.
            </p>
          </Callout>
        </div>
      ) : null}

      {thin.length ? (
        <>
          <Section>Not yet tested</Section>
          <Card>
            <p className="sub">
              Fewer than 4 attempts — no claim either way. These are not weaknesses; they are
              blanks.
            </p>
            <div className="list">
              {thin.map((r) => (
                <div className="list-row" key={r.id}>
                  <div className="grow">
                    <div className="t">{r.name}</div>
                    <div className="s">
                      {r.seen} of {r.total} questions seen
                      {r.attempts ? ` · ${r.attempts} answered` : ''}
                    </div>
                  </div>
                  <button className="btn" onClick={() => drillRule(r.id)}>Test it</button>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : null}
    </div>
  )
}

export function StudyCard() {
  const { epoch, toast } = useApp()
  const card = useAsync(() => api.card(), [epoch])

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Decision rules — study card</h1>
        <p>
          Generated from the taxonomy, so it cannot drift from the rules actually being tested.
        </p>
      </div>
      <div className="btn-row" style={{ marginBottom: 14 }}>
        <Link className="btn" to="/rules">← Back</Link>
        <button
          className="btn"
          onClick={async () => {
            if (!card.data) return
            try {
              await navigator.clipboard.writeText(card.data.text)
              toast('Copied.')
            } catch {
              toast('Could not copy — select and copy manually.', true)
            }
          }}
        >
          Copy to clipboard
        </button>
        <button className="btn" onClick={() => window.print()}>Print</button>
      </div>
      {card.loading ? (
        <Loading />
      ) : card.error || !card.data ? (
        <ErrorNote message={card.error ?? 'No card'} onRetry={card.reload} />
      ) : (
        <pre className="card-text">{card.data.text}</pre>
      )}
    </div>
  )
}
