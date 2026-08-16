/**
 * Branching cases: list, runner, debrief.
 *
 * The runner is deliberately the least designed surface in this app. No score
 * counter, no colour on the options, no progress bar toward a verdict, nothing
 * that tells you how you are doing. A case trains living with a choice whose
 * cost only appears two steps later, and any reassurance between decisions
 * destroys exactly that.
 *
 * The debrief is where the effort goes. It carries the walked path, every
 * option not taken with the reasoning for each, where those branches would have
 * led, and — when a taint fired — the specific decision that fixed the outcome
 * regardless of everything after it.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import type {
  CaseChoice, CaseDebrief, CaseState, DebriefOption, Quality, Verdict,
} from '../api/types'
import { plural, stamp } from '../lib/format'
import { useAsync, useKeys } from '../lib/hooks'
import { Callout, Card, ErrorNote, Loading, Section } from '../ui/primitives'
import { CaseGraph } from '../charts/CaseGraph'
import { NarrationControls, SpeakButton, useNarration } from '../ui/Narration'
import { narrate } from '../lib/speech'

const VERDICT_TONE: Record<string, string> = {
  strong: 'good',
  acceptable: '',
  weak: 'warn',
  failed: 'bad',
}

const QUALITY_TONE: Record<Quality, string> = {
  best: 'good',
  defensible: '',
  poor: 'bad',
}

function VerdictChip({ verdict }: { verdict: Verdict | string }) {
  const tone = VERDICT_TONE[verdict] ?? ''
  return <span className={`chip ${tone}`.trim()}>{verdict || 'unknown'}</span>
}

/** Paragraph-aware rendering — case prose uses blank lines deliberately. */
function Prose({ text, className }: { text: string; className?: string }) {
  return (
    <>
      {String(text)
        .split('\n')
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p, i) => (
          <p key={i} className={className}>{p}</p>
        ))}
    </>
  )
}

// ------------------------------------------------------------------ list

export function CasesHome() {
  const { epoch } = useApp()
  const list = useAsync(() => api.caseList(), [epoch])
  /*
   * `?case=<id>` highlights and scrolls to one case. The Next Session screen
   * names a specific case in its recommendation, and landing on an
   * undifferentiated list would break that promise. It deliberately does not
   * auto-start: a link should not commit you to a fifteen-minute session.
   */
  const wanted = new URLSearchParams(useLocation().search).get('case') ?? ''
  const highlight = useRef<HTMLDivElement | null>(null)
  const narration = useNarration('list')

  useEffect(() => {
    if (wanted && highlight.current) {
      highlight.current.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }
  }, [wanted, list.data])

  if (list.loading) return <div className="wrap"><Loading /></div>
  if (list.error || !list.data) {
    return (
      <div className="wrap">
        <ErrorNote message={list.error ?? 'No cases'} onRetry={list.reload} />
      </div>
    )
  }

  return (
    <div className="wrap narrow">
      <div className="page-head">
        <h1>Cases</h1>
        <p>
          You are dropped into an engagement and make five to eight decisions. The situation
          moves in response, and you find out how it went at the end — not at each step.
          Options are graded best / defensible / poor, because real audit judgment rarely
          divides into right and wrong.
        </p>
      </div>

      <Callout kind="info">
        <p>
          <b>No feedback until the debrief.</b> You will see what happened after each decision,
          never whether it was a good one. Some choices cannot be walked back.
        </p>
      </Callout>

      <NarrationControls n={narration} />

      <div style={{ marginTop: 18 }}>
        {list.data.cases.map((c) => (
          <div key={c.id} ref={c.id === wanted ? highlight : undefined}>
          <Card className={`case-card${c.id === wanted ? ' wanted' : ''}`}>
            <div className="case-head">
              <div className="grow">
                <h3>{c.title}</h3>
                <div className="s">
                  D{c.domain}{c.section} · {c.nodes} decision {plural(c.nodes, 'point')} ·{' '}
                  {c.endings} possible {plural(c.endings, 'ending')} · about {c.minutes} min
                </div>
              </div>
              {c.attempts ? (
                <div className="case-runs">
                  {c.verdicts.slice(-4).map((v, i) => (
                    <VerdictChip key={i} verdict={v} />
                  ))}
                </div>
              ) : null}
            </div>

            <div className="case-topics">
              {c.topics.map((t) => (
                <span className="chip" key={t}>{t}</span>
              ))}
            </div>

            <div className="btn-row" style={{ marginTop: 14 }}>
              {c.open_session ? (
                <>
                  <Link className="btn primary" to={`/cases/run/${c.open_session}`}>
                    Resume — {c.open_decisions} {plural(c.open_decisions, 'decision')} in
                  </Link>
                  <StartButton caseId={c.id} label="Start over" />
                </>
              ) : (
                <StartButton caseId={c.id} label={c.attempts ? 'Play again' : 'Start case'} primary />
              )}
              {c.last_played ? (
                <span className="dim" style={{ fontSize: 12.5 }}>
                  last played {stamp(c.last_played)}
                </span>
              ) : null}
            </div>
          </Card>
          </div>
        ))}
      </div>

      <p className="chart-note" style={{ marginTop: 20 }}>
        Case results are logged separately from drills and exams. A case is not a four-option
        question, so letting it reach item analysis or the scheduler would corrupt both.
      </p>
    </div>
  )
}

function StartButton({ caseId, label, primary }: {
  caseId: string
  label: string
  primary?: boolean
}) {
  const nav = useNavigate()
  const { toast } = useApp()
  const [busy, setBusy] = useState(false)
  return (
    <button
      className={`btn ${primary ? 'primary' : ''}`.trim()}
      disabled={busy}
      onClick={async () => {
        setBusy(true)
        try {
          const data = await api.caseStart(caseId)
          nav(`/cases/run/${data.session}`)
        } catch (err) {
          toast(err instanceof Error ? err.message : String(err), true)
          setBusy(false)
        }
      }}
    >
      {busy ? 'Opening…' : label}
    </button>
  )
}

// ---------------------------------------------------------------- runner

export function CaseRunner() {
  const { session = '' } = useParams()
  const { toast } = useApp()
  const nav = useNavigate()

  const [state, setState] = useState<CaseState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [consequence, setConsequence] = useState<CaseChoice | null>(null)
  const [pending, setPending] = useState(false)
  const started = useRef(Date.now())
  const continueRef = useRef<HTMLButtonElement | null>(null)
  // Keyed on the node id, so moving to the next decision cancels the previous
  // consequence mid-sentence rather than letting the two overlap.
  const narration = useNarration(state?.node?.id ?? '')

  useEffect(() => {
    let live = true
    api.caseGet(session).then(
      (data) => {
        if (!live) return
        if (data.finished) {
          nav(`/cases/debrief/${session}`, { replace: true })
          return
        }
        setState(data)
        started.current = Date.now()
      },
      (err: unknown) => live && setError(err instanceof Error ? err.message : String(err)),
    )
    return () => { live = false }
  }, [session, nav])

  const choose = useCallback(
    async (key: string) => {
      if (!state?.node || pending || consequence) return
      setPending(true)
      try {
        const res = await api.caseChoose(
          session, state.node.id, key, (Date.now() - started.current) / 1000,
        )
        setConsequence(res)
      } catch (err) {
        toast(err instanceof Error ? err.message : String(err), true)
      } finally {
        setPending(false)
      }
    },
    [state, session, pending, consequence, toast],
  )

  const advance = useCallback(() => {
    if (!consequence) return
    if (consequence.finished) {
      nav(`/cases/debrief/${session}`)
      return
    }
    setState((prev) =>
      prev ? { ...prev, node: consequence.next, decisions: consequence.decisions } : prev)
    setConsequence(null)
    started.current = Date.now()
  }, [consequence, nav, session])

  useEffect(() => {
    if (consequence) continueRef.current?.focus()
  }, [consequence])

  useKeys((ev) => {
    if (consequence) {
      if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault()
        advance()
      }
      return
    }
    const keys = state?.node?.options.map((o) => o.key.toUpperCase()) ?? []
    const pressed = ev.key.toUpperCase()
    if (keys.includes(pressed)) {
      ev.preventDefault()
      void choose(pressed)
    }
  }, !!state)

  if (error) {
    return (
      <div className="wrap narrow">
        <ErrorNote message={error} />
        <div className="btn-row" style={{ marginTop: 14 }}>
          <Link className="btn" to="/cases">Back to cases</Link>
        </div>
      </div>
    )
  }
  if (!state || !state.node) return <div className="wrap"><Loading what="Opening the engagement…" /></div>

  const node = state.node
  // Scene-setting belongs before the first decision only. Keyed off the node's
  // own position rather than the trail, so it also behaves on resume.
  const opening = node.position <= 1

  return (
    <>
      <div className="runner-top">
        <div className="meta">{state.case.title}</div>
        {/* Decision count, not progress. Paths differ in length, so there is
            no honest denominator and none is shown. */}
        <div className="meta">Decision {node.position}</div>
        <div className="grow" />
        <Link className="btn ghost" to="/cases">Save &amp; exit</Link>
      </div>

      <div className="wrap narrow">
        {opening ? (
          <Card className="case-opening">
            <Prose text={state.opening} />
            <SpeakButton n={narration} text={narrate.opening(state)}
                         label="Read the brief aloud" />
          </Card>
        ) : (
          /* Still reachable, because a 12-minute case outlives your memory of
             the brief — but collapsed, so it does not compete with the decision. */
          <details className="case-brief">
            <summary>The brief</summary>
            <Prose text={state.opening} />
            <SpeakButton n={narration} text={narrate.opening(state)}
                         label="Read the brief aloud" />
          </details>
        )}

        <div className="qcard" style={{ marginTop: opening ? 20 : 0 }}>
          <div className="case-situation">
            <Prose text={node.situation} />
            {/* Situation and prompt only. The options below are deliberately
                not narrated — see lib/speech.ts. */}
            <SpeakButton n={narration} text={narrate.situation(node)}
                         label="Read the situation aloud" />
          </div>
          <p className="stem">{node.prompt}</p>

          <div className="options">
            {node.options.map((o) => (
              <button
                key={o.key}
                className={`opt ${consequence ? 'static' : ''} ${
                  consequence && consequence.chosen === o.key.toUpperCase() ? 'selected' : ''
                } ${consequence && consequence.chosen !== o.key.toUpperCase() ? 'dimmed' : ''}`.trim()}
                disabled={!!consequence || pending}
                onClick={() => void choose(o.key)}
              >
                <span className="key">{o.key}</span>
                <span className="body">{o.text}</span>
              </button>
            ))}
          </div>

          {consequence ? (
            <>
              {/* Neutral narration. No verdict, no colour, nothing that says
                  whether this was a good call. */}
              <div className="consequence">
                <div className="kicker">What happens</div>
                <Prose text={consequence.consequence} />
                <SpeakButton n={narration} text={narrate.consequence(consequence)}
                             label="Read this aloud" />
              </div>
              <div className="runner-foot">
                <button className="btn primary" ref={continueRef} onClick={advance}>
                  {consequence.finished ? 'See how it went' : 'Continue'}
                </button>
                <span className="kbd-hint">press <kbd>Enter</kbd></span>
              </div>
            </>
          ) : (
            <div className="runner-foot">
              <span className="kbd-hint">
                press{' '}
                {node.options.map((o) => <kbd key={o.key}>{o.key}</kbd>)}
              </span>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// --------------------------------------------------------------- debrief

export function CaseDebriefScreen() {
  const { session = '' } = useParams()
  const debrief = useAsync<CaseDebrief>(() => api.caseDebrief(session), [session])
  const narration = useNarration(session)

  if (debrief.loading) return <div className="wrap"><Loading what="Building the debrief…" /></div>
  if (debrief.error || !debrief.data) {
    return (
      <div className="wrap">
        <ErrorNote message={debrief.error ?? 'No debrief'} onRetry={debrief.reload} />
        <div className="btn-row" style={{ marginTop: 14 }}>
          <Link className="btn" to="/cases">Back to cases</Link>
        </div>
      </div>
    )
  }

  const d = debrief.data
  const { counts } = d

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>{d.case.title}</h1>
        <p>
          D{d.case.domain}{d.case.section} · {d.decisions}{' '}
          {plural(d.decisions, 'decision')}
        </p>
      </div>

      <Card>
        <div className="ending-head">
          <VerdictChip verdict={d.ending.verdict} />
          <h2 className="ending-title">{d.ending.title}</h2>
        </div>
        <Prose text={d.ending.narrative} className="ending-narrative" />
        <SpeakButton n={narration} text={narrate.endingNarrative(d.ending)}
                     label="Read the outcome aloud" />
        <div className="rule-note" style={{ marginTop: 16 }}>
          <div className="kicker">What this path got right or wrong</div>
          <Prose text={d.ending.why} />
        </div>
      </Card>

      {/* The most valuable thing this feature can say. */}
      {d.overridden && d.override ? (
        <>
          <Section>The decision that fixed this</Section>
          <Card className="override">
            <p className="override-lead">
              Your path through the graph ended at{' '}
              <b>{d.graph_ending?.title}</b> ({d.graph_ending?.verdict}). That is not the
              outcome you got. It was determined at{' '}
              <b>decision {d.override.decision} of {d.override.of}</b> —{' '}
              {d.override.decisions_before_end}{' '}
              {plural(d.override.decisions_before_end, 'decision')} before the end — and nothing
              you chose afterwards could recover it.
            </p>
            <div className="override-choice">
              <div className="s">{d.override.prompt}</div>
              <div className="t">
                <span className="chip bad">{d.override.chosen}</span> {d.override.text}
              </div>
            </div>
            <div className="rule-note" style={{ marginTop: 14 }}>
              <div className="kicker">Why it could not be walked back</div>
              <Prose text={d.override.why} />
            </div>
          </Card>
        </>
      ) : null}

      <Section hint="a profile, not a score">Your judgments</Section>
      <Card>
        <div className="counts">
          <div className="count good">
            <div className="n">{counts.best}</div><div className="l">best</div>
          </div>
          <div className="count">
            <div className="n">{counts.defensible}</div><div className="l">defensible</div>
          </div>
          <div className="count bad">
            <div className="n">{counts.poor}</div><div className="l">poor</div>
          </div>
        </div>
        <p className="sub" style={{ margin: '14px 0 0' }}>
          Deliberately not a percentage. A path is a set of judgments plus an outcome, and
          collapsing that to one number throws away the part that teaches. A defensible choice
          is one a competent auditor could make and defend — slower or less complete, but not a
          mistake.
        </p>
      </Card>

      {/* The map first: one thread through a graph reads very differently
          once the graph it came from is visible. */}
      <Section hint="your thread, and the ones you did not walk">
        The whole case
      </Section>
      <Card>
        <CaseGraph graph={d.graph} />
      </Card>

      <Section hint="every option, including the ones you did not take">
        Decision by decision
      </Section>
      {d.walk.map((step) => (
        <Card key={step.index} className="walk-step">
          <div className="walk-head">
            <span className="chip mono">{step.index}</span>
            <span className="walk-prompt">{step.prompt}</span>
          </div>
          <div className="case-situation small">
            <Prose text={step.situation} />
          </div>

          <div className="options" style={{ marginTop: 12 }}>
            {step.options.map((o) => (
              <DebriefOptionRow
                key={o.key}
                option={o}
                endings={d.endings_index}
                isBest={o.key === step.best}
              />
            ))}
          </div>
        </Card>
      ))}

      {d.principles.length ? (
        <>
          <Section>Decision rules this case turns on</Section>
          <Card>
            <div className="btn-row">
              {d.principles.map((p) => (
                <span className="chip" key={p}>{p}</span>
              ))}
            </div>
            <p className="sub" style={{ margin: '12px 0 0' }}>
              Cases are not yet wired into the decision-rule diagnostic — that waits until the
              format has been proven against real use, so it cannot disturb a working
              instrument.
            </p>
          </Card>
        </>
      ) : null}

      <div className="btn-row" style={{ marginTop: 20 }}>
        <Link className="btn primary" to="/cases">Back to cases</Link>
        <Link className="btn" to="/">Dashboard</Link>
      </div>
    </div>
  )
}

function DebriefOptionRow({ option, endings, isBest }: {
  option: DebriefOption
  endings: Record<string, { title: string; verdict: string }>
  isBest: boolean
}) {
  const tone = QUALITY_TONE[option.quality] ?? ''
  const landing = endings[option.leads_to]

  return (
    <div
      className={[
        'opt', 'static', 'debrief-opt',
        option.chosen ? 'chosen-path' : '',
        option.quality === 'best' ? 'correct' : '',
        option.chosen && option.quality === 'poor' ? 'chosen-wrong' : '',
        !option.chosen && option.quality !== 'best' ? 'dimmed' : '',
      ].filter(Boolean).join(' ')}
    >
      <span className="key">{option.key}</span>
      <span className="body">
        <span className="opt-flags">
          {option.chosen ? <span className="chip">you chose this</span> : null}
          {isBest ? <span className="chip good">best</span> : (
            <span className={`chip ${tone}`.trim()}>{option.quality}</span>
          )}
          {option.taint ? (
            <span className="chip bad">unrecoverable · {option.taint}</span>
          ) : null}
          {landing ? (
            <span className={`chip ${VERDICT_TONE[landing.verdict] ?? ''}`.trim()}>
              {option.chosen ? 'ended: ' : 'would have ended: '}{landing.title}
            </span>
          ) : null}
        </span>
        {option.text}
        <span className="why" style={{ display: 'block' }}>
          {option.why}
        </span>
      </span>
    </div>
  )
}
