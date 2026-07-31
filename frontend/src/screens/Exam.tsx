/**
 * Mock exam — blueprint-weighted, timed, no feedback until submission.
 *
 * Three rules shape this screen:
 *
 * 1. The clock only runs while a sitting is open and can only move forward. The
 *    browser owns it during a sitting and reports elapsed time to the server, so
 *    a closed tab cannot keep it running and a reloaded one cannot rewind it.
 * 2. No answer key reaches the client until submission. Nothing is prefetched.
 * 3. The scaled score is an approximation of an undisclosed process. It is never
 *    labelled a prediction, and the caveat travels with the number.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import type { ExamResult, ExamState, Letter } from '../api/types'
import { hms, LETTERS, pct, plural, stamp } from '../lib/format'
import { useAsync, useKeys } from '../lib/hooks'
import {
  BarRow, Callout, Card, Empty, ErrorNote, Loading, Section,
} from '../ui/primitives'
import { OptionList, QuestionMeta, RuleNote } from '../ui/QuestionView'
import { intervalOf } from '../lib/format'

export function ExamHome() {
  const { boot, epoch, toast } = useApp()
  const nav = useNavigate()
  const list = useAsync(() => api.examList(), [epoch])
  const [n, setN] = useState(boot.exam?.questions ?? 150)
  const [minutes, setMinutes] = useState(boot.exam?.minutes ?? 240)
  const [domain, setDomain] = useState('')
  const [busy, setBusy] = useState(false)

  const start = async () => {
    setBusy(true)
    try {
      const data = await api.examNew({ n, minutes, domain: domain || undefined })
      nav(`/exam/run/${data.id}`)
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), true)
      setBusy(false)
    }
  }

  return (
    <div className="wrap narrow">
      <div className="page-head">
        <h1>Mock exam</h1>
        <p>
          Blueprint-weighted, timed, no feedback until you submit. The real thing is{' '}
          {boot.exam?.questions ?? 150} questions in {boot.exam?.minutes ?? 240} minutes
          {boot.exam?.verified_on ? ` (format verified ${boot.exam.verified_on})` : ''}.
        </p>
      </div>

      <Card>
        <div className="grid c3">
          <div className="field">
            <label htmlFor="e-n">Questions</label>
            <select id="e-n" value={n} onChange={(e) => setN(Number(e.target.value))}>
              {[150, 100, 75, 50, 25].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="e-min">Minutes</label>
            <select id="e-min" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>
              {[240, 160, 120, 80, 40].map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="e-dom">Scope</label>
            <select id="e-dom" value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">All domains (weighted)</option>
              {boot.domains.map((d) => (
                <option key={d.id} value={d.id}>D{d.id} only</option>
              ))}
            </select>
          </div>
        </div>
        <button className="btn primary" onClick={start} disabled={busy}>
          {busy ? 'Building…' : 'Start exam'}
        </button>
      </Card>

      {list.data?.exams.length ? (
        <>
          <Section>Saved exams</Section>
          <Card>
            <div className="list">
              {list.data.exams.map((e) => (
                <div className="list-row" key={e.id}>
                  <div className="grow">
                    <div className="t">
                      {e.submitted ? 'Submitted' : 'In progress'} ·{' '}
                      <span className="mono">{e.id}</span>
                    </div>
                    <div className="s">
                      {stamp(e.created)} · {e.answered}/{e.total} answered ·{' '}
                      {hms(e.elapsed)} of {hms(e.duration)}
                    </div>
                  </div>
                  <Link
                    className={`btn ${e.submitted ? '' : 'primary'}`.trim()}
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
    </div>
  )
}

// ---------------------------------------------------------------- runner

export function ExamRunner() {
  const { id = '' } = useParams()
  const { toast } = useApp()
  const nav = useNavigate()

  const [state, setState] = useState<ExamState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [answers, setAnswers] = useState<Record<string, Letter>>({})
  const [flagged, setFlagged] = useState<Set<string>>(new Set())
  const [index, setIndex] = useState(0)
  const [left, setLeft] = useState(0)
  const [submitting, setSubmitting] = useState(false)

  // The clock: server-recorded elapsed plus time in this sitting.
  const baseElapsed = useRef(0)
  const sittingStart = useRef(Date.now())
  const questionStart = useRef(Date.now())
  const submitted = useRef(false)

  const elapsed = useCallback(
    () => baseElapsed.current + (Date.now() - sittingStart.current) / 1000,
    [],
  )

  useEffect(() => {
    let live = true
    api.examGet(id).then(
      (data) => {
        if (!live) return
        if (data.submitted) {
          nav(`/exam/result/${id}`, { replace: true })
          return
        }
        setState(data)
        setAnswers({ ...data.answers })
        setFlagged(new Set(data.flagged))
        setIndex(data.position || 0)
        baseElapsed.current = data.elapsed
        sittingStart.current = Date.now()
        questionStart.current = Date.now()
        setLeft(data.duration - data.elapsed)
        if (data.shortfall && Object.keys(data.shortfall).length) {
          toast('Bank could not fill the blueprint — some domains are short.')
        }
      },
      (err: unknown) => live && setError(err instanceof Error ? err.message : String(err)),
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const submit = useCallback(
    async (auto: boolean) => {
      if (!state || submitted.current) return
      const blank = state.questions.length - Object.keys(answers).length
      if (
        !auto && blank > 0 &&
        !window.confirm(
          `${blank} ${plural(blank, 'question')} unanswered. They will score as incorrect. Submit anyway?`,
        )
      ) return

      submitted.current = true
      setSubmitting(true)
      try {
        await api.examSubmit(state.id, elapsed())
        nav(`/exam/result/${state.id}`, { replace: true })
      } catch (err) {
        submitted.current = false
        setSubmitting(false)
        toast(err instanceof Error ? err.message : String(err), true)
      }
    },
    [state, answers, elapsed, nav, toast],
  )

  // Tick the clock locally; report upward periodically so a crash loses little.
  useEffect(() => {
    if (!state) return
    const timer = window.setInterval(() => {
      const remaining = state.duration - elapsed()
      setLeft(remaining)
      if (remaining <= 0 && !submitted.current) {
        toast('Time expired — submitting.')
        void submit(true)
        return
      }
      if (Math.round(elapsed()) % 20 === 0) {
        api.examTick(state.id, elapsed()).catch(() => {})
      }
    }, 1000)
    return () => window.clearInterval(timer)
  }, [state, elapsed, submit, toast])

  const question = state?.questions[index] ?? null

  const choose = useCallback(
    async (letter: Letter | '') => {
      if (!state || !question) return
      setAnswers((prev) => {
        const next = { ...prev }
        if (letter) next[question.id] = letter
        else delete next[question.id]
        return next
      })
      const spent = (Date.now() - questionStart.current) / 1000
      questionStart.current = Date.now()
      try {
        await api.examAnswer(state.id, question.id, letter, spent)
      } catch (err) {
        toast(err instanceof Error ? err.message : String(err), true)
      }
      if (letter && index < state.questions.length - 1) {
        window.setTimeout(() => setIndex((i) => Math.min(i + 1, state.questions.length - 1)), 130)
      }
    },
    [state, question, index, toast],
  )

  const go = useCallback(
    (n: number) => {
      if (!state) return
      const clamped = Math.max(0, Math.min(state.questions.length - 1, n))
      setIndex(clamped)
      questionStart.current = Date.now()
      api.examPosition(state.id, clamped).catch(() => {})
    },
    [state],
  )

  const toggleFlag = useCallback(() => {
    if (!state || !question) return
    setFlagged((prev) => {
      const next = new Set(prev)
      if (next.has(question.id)) next.delete(question.id)
      else next.add(question.id)
      return next
    })
    api.examFlag(state.id, question.id).catch(() => {})
  }, [state, question])

  useKeys((ev) => {
    if (!state) return
    const byLetter = LETTERS.indexOf(ev.key.toUpperCase() as Letter)
    const byNumber = '1234'.indexOf(ev.key)
    const idx = byLetter >= 0 ? byLetter : byNumber
    if (idx >= 0) {
      ev.preventDefault()
      void choose(LETTERS[idx])
      return
    }
    if (ev.key === 'ArrowRight' || ev.key === 'Enter') {
      ev.preventDefault()
      go(index + 1)
    } else if (ev.key === 'ArrowLeft') {
      ev.preventDefault()
      go(index - 1)
    } else if (ev.key.toUpperCase() === 'F') {
      ev.preventDefault()
      toggleFlag()
    }
  }, !!state)

  if (error) {
    return (
      <div className="wrap narrow">
        <ErrorNote message={error} />
        <div className="btn-row" style={{ marginTop: 14 }}>
          <Link className="btn" to="/exam">Back to exams</Link>
        </div>
      </div>
    )
  }
  if (!state || !question) return <div className="wrap"><Loading what="Loading exam…" /></div>

  const answeredCount = Object.keys(answers).length
  const timerClass = left < 300 ? 'crit' : left < 900 ? 'warn' : ''

  return (
    <>
      <div className="runner-top">
        <div className={`timer ${timerClass}`.trim()} role="timer" aria-live="off">
          {hms(left)}
        </div>
        <div className="meta">Q {index + 1} / {state.questions.length}</div>
        <div className="meta">{answeredCount} answered · {flagged.size} flagged</div>
        <div className="grow" />
        <button
          className="btn ghost"
          onClick={async () => {
            await api.examTick(state.id, elapsed()).catch(() => {})
            toast('Saved. The clock is stopped.')
            nav('/exam')
          }}
        >
          Save &amp; exit
        </button>
        <button className="btn primary" onClick={() => submit(false)} disabled={submitting}>
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </div>

      <div className="wrap">
        <div className="qcard">
          <div className="qmeta">
            <span className="chip mono">{index + 1}</span>
            <button
              className={`chip ${flagged.has(question.id) ? 'warn' : ''}`.trim()}
              onClick={toggleFlag}
              aria-pressed={flagged.has(question.id)}
            >
              {flagged.has(question.id) ? '● Flagged' : '○ Flag for review'}
            </button>
          </div>
          <p className="stem">{question.stem}</p>

          <OptionList
            question={question}
            reveal={null}
            chosen={answers[question.id] ?? null}
            onChoose={(l) => void choose(l)}
          />

          <div className="runner-foot">
            <button className="btn" onClick={() => go(index - 1)} disabled={index === 0}>
              ← Previous
            </button>
            <button
              className="btn"
              onClick={() => go(index + 1)}
              disabled={index >= state.questions.length - 1}
            >
              Next →
            </button>
            <button className="btn ghost" onClick={() => void choose('')}>
              Clear answer
            </button>
            <span className="kbd-hint">
              <kbd>A</kbd>–<kbd>D</kbd> answer · <kbd>F</kbd> flag · <kbd>←</kbd><kbd>→</kbd> move
            </span>
          </div>
        </div>

        <Section>Question palette</Section>
        <Card>
          <div className="pal-key">
            <span><i className="a" />answered</span>
            <span><i className="f" />flagged</span>
            <span><i className="c" />current</span>
            <span><i />unanswered</span>
          </div>
          <div className="palette">
            {state.questions.map((q, n) => (
              <button
                key={q.id}
                className={[
                  'pal',
                  answers[q.id] ? 'answered' : '',
                  flagged.has(q.id) ? 'flagged' : '',
                  n === index ? 'current' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => go(n)}
                aria-label={`Question ${n + 1}${answers[q.id] ? ', answered' : ''}${flagged.has(q.id) ? ', flagged' : ''}`}
                aria-current={n === index}
              >
                {n + 1}
              </button>
            ))}
          </div>
        </Card>
      </div>
    </>
  )
}

// ---------------------------------------------------------------- result

export function ExamResultScreen() {
  const { id = '' } = useParams()
  const result = useAsync<ExamResult>(() => api.examResult(id), [id])

  if (result.loading) return <div className="wrap"><Loading what="Scoring…" /></div>
  if (result.error || !result.data) {
    return (
      <div className="wrap">
        <ErrorNote message={result.error ?? 'No result'} onRetry={result.reload} />
      </div>
    )
  }

  const r = result.data
  const weak = r.by_domain
    .filter((d) => d.asked >= 5 && d.accuracy < 0.65)
    .sort((a, b) => b.cost - a.cost)

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Exam result</h1>
        <p className="mono">{r.id}</p>
      </div>

      <Card>
        <div className="score-hero">
          <div className={`big ${r.passed ? 'good' : 'bad'}`}>{r.scaled}</div>
          <div>
            <div style={{ fontSize: 17 }}>estimated scaled score</div>
            <div className="dim" style={{ fontSize: 13 }}>
              {r.correct}/{r.total} raw ({pct(r.raw, 1)}) · {hms(r.elapsed)} of {hms(r.duration)}
              {r.unanswered ? ` · ${r.unanswered} unanswered` : ''}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 16 }}>
          <Callout>
            <p>
              <b>This is an approximation, not ISACA's number.</b> ISACA scales raw scores with an
              undisclosed psychometric process and the raw threshold moves between exam forms. The
              pass mark is {r.pass_mark}; treat anything within about 50 points of it as too close
              to call. It is not a prediction of your result.
            </p>
          </Callout>
        </div>
      </Card>

      <Section hint="whisker is the 95% interval on this exam's sample">By domain</Section>
      <Card>
        {r.by_domain.map((d) => (
          <BarRow
            key={d.domain}
            label={`D${d.domain} ${d.name}`}
            sub={`${d.weight}% of exam · ${d.asked} asked`}
            stat={intervalOf(d.correct, d.asked)}
            right={`${d.correct}/${d.asked}`}
          />
        ))}
      </Card>

      {weak.length ? (
        <>
          <Section>Where the lost marks actually are</Section>
          <Card>
            <p className="sub">
              Accuracy gap multiplied by exam weight. A 60% in a 26% domain costs more than a
              50% in a 12% one.
            </p>
            {weak.map((d) => (
              <div className="list-row" key={d.domain}>
                <div className="grow">
                  <div className="t">D{d.domain} {d.name}</div>
                  <div className="s">
                    {pct(d.accuracy)} accuracy · {d.weight}% of the exam
                  </div>
                </div>
                <div className="right">
                  <div className="t" style={{ color: 'var(--bad)' }}>−{d.cost.toFixed(1)}%</div>
                  <div className="s">of the exam</div>
                </div>
              </div>
            ))}
          </Card>
        </>
      ) : null}

      {r.slowest.length ? (
        <>
          <Section>Slowest questions</Section>
          <Card>
            <div className="list">
              {r.slowest.map((s) => (
                <div className="list-row" key={s.id}>
                  <span className="mono">{s.id}</span>
                  <div className="grow"><div className="s">{s.topic}</div></div>
                  <span className="chip mono">{s.seconds.toFixed(0)}s</span>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : null}

      {r.guessed_right.length ? (
        <>
          <Section>Flagged but correct ({r.guessed_right.length})</Section>
          <Card>
            <p className="sub">
              You were unsure and got there anyway. Worth revisiting even though the score looks fine.
            </p>
            <div className="list">
              {r.guessed_right.map((g) => (
                <div className="list-row" key={g.id}>
                  <span className="mono">{g.id}</span>
                  <div className="grow"><div className="s">{g.topic}</div></div>
                </div>
              ))}
            </div>
          </Card>
        </>
      ) : null}

      <Section>Review the {r.missed.length} you missed</Section>
      {r.missed.length ? (
        r.missed.map((q) => (
          <Card key={q.id} className="review-card">
            <QuestionMeta
              question={q}
              extra={
                <>
                  {q.chosen
                    ? <span className="chip bad">you chose {q.chosen}</span>
                    : <span className="chip warn">left blank</span>}
                  <span className="chip good">answer {q.answer}</span>
                </>
              }
            />
            <p className="stem" style={{ fontSize: 15.5 }}>{q.stem}</p>
            <OptionList question={q} reveal={q} chosen={q.chosen} />
            {q.principle ? <RuleNote principle={q.principle} showScope={false} /> : null}
          </Card>
        ))
      ) : (
        <Card><Empty>Nothing missed.</Empty></Card>
      )}

      <div className="btn-row" style={{ marginTop: 20 }}>
        <Link className="btn" to="/exam">Back to exams</Link>
        <Link className="btn" to="/">Dashboard</Link>
      </div>
    </div>
  )
}
