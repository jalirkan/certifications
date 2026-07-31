/**
 * Short form — Cold Read and Autopsy.
 *
 * These results are logged to a different file server-side and never blended
 * into drill or exam accuracy. A five-second answer is not the same evidence as
 * a worked scenario, and letting the two share a headline number would quietly
 * corrupt the one figure the whole tool is built to keep honest. Every surface
 * here says so.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import type {
  AskType, AutopsyResult, ColdReadResult, GameQuestion, GameStart, Letter,
} from '../api/types'
import { LETTERS, pct } from '../lib/format'
import { useAsync } from '../lib/hooks'
import { BarRow, Callout, Card, Loading, Section } from '../ui/primitives'
import { MisreadMatrix } from '../charts/MisreadMatrix'
import { intervalOf } from '../lib/format'

/**
 * Display labels for the matrix axes.
 *
 * The server owns the ask types; these ids come back inside game payloads, and
 * fetching one purely to label a chart would mean firing a side-effectful POST
 * on page load. Any id missing here renders as itself, so the worst case of
 * drift is a less pretty axis label, never a wrong one.
 */
const ASK_LABELS: Record<string, string> = {
  first: 'FIRST / NEXT',
  risk: 'GREATEST RISK',
  control: 'BEST CONTROL',
  evidence: 'BEST EVIDENCE',
  definition: 'DEFINITION',
}

function askTypesFrom(misreads: { expected: string; read: string }[]): AskType[] {
  const ids = new Set<string>()
  for (const m of misreads) {
    ids.add(m.expected)
    ids.add(m.read)
  }
  return [...ids].map((id) => ({ id, label: ASK_LABELS[id] ?? id, gloss: '' }))
}

export function GamesHome() {
  const { epoch } = useApp()
  const stats = useAsync(() => api.gameStats(), [epoch])

  return (
    <div className="wrap narrow">
      <div className="page-head">
        <h1>Short form</h1>
        <p>
          Two-minute drills that sharpen the substrate the judgment runs on. Results are kept
          out of your real accuracy on purpose — a five-second answer is not the same evidence
          as a worked scenario.
        </p>
      </div>

      <div className="grid c2">
        <Card>
          <h3>Cold Read</h3>
          <p className="sub">
            Options hidden. Name what the question is <em>asking for</em>, predict the answer,
            then look.
          </p>
          <p style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>
            Targets the most common way to lose marks on material you actually know: answering a
            question you misread.
          </p>
          <div className="btn-row" style={{ marginTop: 14 }}>
            <Link className="btn primary" to="/games/coldread">Start · 10 items</Link>
          </div>
        </Card>
        <Card>
          <h3>Autopsy</h3>
          <p className="sub">
            The answer is given. Match each wrong option to the explanation of why it fails.
          </p>
          <p style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>
            Teaches how the traps are built, which is the part that transfers to questions you
            have never seen.
          </p>
          <div className="btn-row" style={{ marginTop: 14 }}>
            <Link className="btn primary" to="/games/autopsy">Start · 8 items</Link>
          </div>
        </Card>
      </div>

      {stats.data?.total ? (
        <>
          <Section>Results</Section>
          <Card>
            {stats.data.by_game.map((g) => (
              <BarRow
                key={g.game}
                label={g.game === 'coldread' ? 'Cold Read' : 'Autopsy'}
                sub={`${g.n} items · ${g.n ? (g.secs / g.n).toFixed(0) : 0}s each`}
                stat={intervalOf(g.ok, g.n)}
              />
            ))}
            <p className="sub" style={{ margin: '14px 0 0' }}>
              Kept in a separate log from drills and exams. These never reach headline accuracy,
              item analysis, or the scheduler.
            </p>
          </Card>

          <Section>Misread matrix</Section>
          <Card>
            <MisreadMatrix
              stats={stats.data}
              askTypes={askTypesFrom(stats.data.misreads)}
            />
          </Card>
        </>
      ) : stats.loading ? (
        <Loading />
      ) : null}
    </div>
  )
}

// ------------------------------------------------------------- shared top

function GameTop({
  label, index, total, right, answered,
}: {
  label: string
  index: number
  total: number
  right: number
  answered: number
}) {
  return (
    <div className="runner-top">
      <div className="progress">
        <span style={{ width: `${(index / Math.max(1, total)) * 100}%` }} />
      </div>
      <div className="meta">{label} · {index + 1} of {total}</div>
      <div className="meta">{answered ? `${right}/${answered}` : ''}</div>
      <div className="grow" />
      <Link className="btn ghost" to="/games">End</Link>
    </div>
  )
}

function GameDone({ label, right, answered }: {
  label: string
  right: number
  answered: number
}) {
  const acc = answered ? right / answered : 0
  return (
    <div className="wrap narrow">
      <div className="page-head"><h1>{label} complete</h1></div>
      <Card>
        <div className="score-hero">
          <div className={`big ${acc >= 0.7 ? 'good' : ''}`.trim()}>{right}/{answered}</div>
          <div>
            <div style={{ fontSize: 19 }}>{pct(acc)}</div>
            <div className="dim" style={{ fontSize: 13 }}>
              kept out of your drill and exam accuracy
            </div>
          </div>
        </div>
      </Card>
      <div className="btn-row" style={{ marginTop: 16 }}>
        <Link className="btn primary" to="/games">Back to short form</Link>
        <Link className="btn" to="/">Dashboard</Link>
      </div>
    </div>
  )
}

/** Shared loader for both games. */
function useGame(game: 'coldread' | 'autopsy', n: number) {
  const [data, setData] = useState<GameStart | null>(null)
  const [error, setError] = useState<string | null>(null)
  const started = useRef(false)

  useEffect(() => {
    if (started.current) return
    started.current = true
    api.gameStart(game, n).then(
      setData,
      (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
    )
  }, [game, n])

  return { data, error }
}

// ---------------------------------------------------------------- coldread

type ColdStage = 'ask' | 'committed' | 'revealed'

export function ColdRead() {
  const { data, error } = useGame('coldread', 10)
  const { toast } = useApp()

  const [index, setIndex] = useState(0)
  const [stage, setStage] = useState<ColdStage>('ask')
  const [read, setRead] = useState<string | null>(null)
  const [result, setResult] = useState<ColdReadResult | null>(null)
  const [score, setScore] = useState({ right: 0, answered: 0 })
  const [done, setDone] = useState(false)
  const start = useRef(Date.now())

  const question = data?.questions[index] ?? null

  useEffect(() => { start.current = Date.now() }, [index])

  const commit = async (askId: string) => {
    if (!data || !question || stage !== 'ask') return
    setRead(askId)
    setStage('committed')
    try {
      const res = await api.coldReadAnswer({
        question_id: question.id,
        session: data.session,
        read: askId,
        seconds: (Date.now() - start.current) / 1000,
      })
      setResult(res)
      setScore((s) => ({
        right: s.right + (res.read_correct ? 1 : 0),
        answered: s.answered + 1,
      }))
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), true)
      setStage('ask')
      setRead(null)
    }
  }

  const advance = async (selfReport?: string) => {
    if (data && question && selfReport && result) {
      try {
        await api.coldReadAnswer({
          question_id: question.id,
          session: data.session,
          read: result.read,
          self_report: selfReport,
          seconds: 0,
        })
      } catch {
        /* the graded part already landed; the self-report is a bonus */
      }
    }
    if (!data) return
    if (index + 1 >= data.questions.length) { setDone(true); return }
    setIndex((i) => i + 1)
    setStage('ask')
    setRead(null)
    setResult(null)
  }

  if (error) {
    return (
      <div className="wrap narrow">
        <Callout kind="bad"><p><b>Could not start Cold Read.</b> {error}</p></Callout>
        <div className="btn-row" style={{ marginTop: 12 }}>
          <Link className="btn" to="/games">Back</Link>
        </div>
      </div>
    )
  }
  if (!data || !question) return <div className="wrap"><Loading what="Preparing…" /></div>
  if (done) return <GameDone label="Cold Read" right={score.right} answered={score.answered} />

  return (
    <>
      <GameTop label="Cold Read" index={index} total={data.questions.length}
               right={score.right} answered={score.answered} />
      <div className="wrap narrow">
        <div className="qcard">
          <div className="qmeta">
            <span className="chip mono">{question.tag}</span>
            <span className="chip">{question.topic}</span>
          </div>
          <p className="stem">{question.stem}</p>

          {stage === 'ask' || stage === 'committed' ? (
            <>
              <div style={{ marginBottom: 16 }}>
                <Callout kind="info">
                  <p>The options are hidden. What is this question <b>asking for</b>?</p>
                </Callout>
              </div>
              <div className="options">
                {data.ask_types.map((a, n) => {
                  let cls = 'opt'
                  if (result) {
                    if (a.id === result.expected) cls += ' correct'
                    else if (a.id === read) cls += ' chosen-wrong'
                    else cls += ' dimmed'
                    cls += ' static'
                  }
                  const inner = (
                    <>
                      <span className="key">{n + 1}</span>
                      <span className="body">
                        <b>{a.label}</b>
                        <br />
                        <span className="dim" style={{ fontSize: 13 }}>{a.gloss}</span>
                      </span>
                    </>
                  )
                  return result ? (
                    <div key={a.id} className={cls}>{inner}</div>
                  ) : (
                    <button key={a.id} className={cls} onClick={() => commit(a.id)}>
                      {inner}
                    </button>
                  )
                })}
              </div>
            </>
          ) : null}

          {result && stage === 'committed' ? (
            <>
              <div style={{ margin: '18px 0' }}>
                <Callout kind={result.read_correct ? 'info' : 'warn'}>
                  <p>
                    {result.read_correct
                      ? <><b>Right.</b> Now say your answer out loud before you look.</>
                      : <><b>Misread.</b> Commit to an answer anyway, then look.</>}
                  </p>
                </Callout>
              </div>
              <button className="btn primary" onClick={() => setStage('revealed')} autoFocus>
                Reveal the options
              </button>
            </>
          ) : null}

          {result && stage === 'revealed' ? (
            <>
              <div className="options" style={{ marginTop: 18 }}>
                {LETTERS.map((L) => (
                  <div key={L} className={`opt static ${L === result.answer ? 'correct' : 'dimmed'}`}>
                    <span className="key">{L}</span>
                    <span className="body">
                      {result.options[L as Letter]}
                      {L === result.answer ? (
                        <span className="why good" style={{ display: 'block' }}>
                          <b>Why this is right</b> — {result.why_correct}
                        </span>
                      ) : null}
                    </span>
                  </div>
                ))}
              </div>
              <Card>
                <h3>Did your prediction match?</h3>
                <p className="sub">Self-reported and kept separate from the graded part.</p>
                <div className="btn-row">
                  <button className="btn" onClick={() => advance('y')}>Matched</button>
                  <button className="btn" onClick={() => advance('c')}>Close</button>
                  <button className="btn" onClick={() => advance('n')}>Missed it</button>
                  <button className="btn ghost" onClick={() => advance()}>Skip</button>
                </div>
              </Card>
            </>
          ) : null}
        </div>
      </div>
    </>
  )
}

// ----------------------------------------------------------------- autopsy

export function Autopsy() {
  const { data, error } = useGame('autopsy', 8)
  const { toast } = useApp()

  const [index, setIndex] = useState(0)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [result, setResult] = useState<AutopsyResult | null>(null)
  const [score, setScore] = useState({ right: 0, answered: 0 })
  const [done, setDone] = useState(false)
  const start = useRef(Date.now())

  const question: GameQuestion | null = data?.questions[index] ?? null

  useEffect(() => {
    start.current = Date.now()
    setMapping({})
    setResult(null)
  }, [index])

  const check = useCallback(async () => {
    if (!data || !question || result) return
    try {
      const res = await api.autopsyAnswer({
        question_id: question.id,
        session: data.session,
        mapping,
        seconds: (Date.now() - start.current) / 1000,
      })
      setResult(res)
      setScore((s) => ({
        right: s.right + (res.correct ? 1 : 0),
        answered: s.answered + 1,
      }))
    } catch (err) {
      toast(err instanceof Error ? err.message : String(err), true)
    }
  }, [data, question, mapping, result, toast])

  if (error) {
    return (
      <div className="wrap narrow">
        <Callout kind="bad"><p><b>Could not start Autopsy.</b> {error}</p></Callout>
        <div className="btn-row" style={{ marginTop: 12 }}>
          <Link className="btn" to="/games">Back</Link>
        </div>
      </div>
    )
  }
  if (!data || !question) return <div className="wrap"><Loading what="Preparing…" /></div>
  if (done) return <GameDone label="Autopsy" right={score.right} answered={score.answered} />

  const distractors = question.distractors ?? []
  const explanations = question.explanations ?? []
  const ready = distractors.every((d) => mapping[d])

  return (
    <>
      <GameTop label="Autopsy" index={index} total={data.questions.length}
               right={score.right} answered={score.answered} />
      <div className="wrap">
        <div className="qcard">
          <div className="qmeta">
            <span className="chip mono">{question.tag}</span>
            <span className="chip">{question.topic}</span>
            <span className="chip good">answer {question.answer}</span>
          </div>
          <p className="stem">{question.stem}</p>

          <div className="options">
            {LETTERS.map((L) => {
              const isAnswer = L === question.answer
              const isDistractor = distractors.includes(L)
              const truthLabel = result?.truth?.[L]
              const mine = mapping[L]
              return (
                <div
                  key={L}
                  className={`opt static ${isAnswer ? 'correct' : ''} ${
                    result && isDistractor ? (mine === truthLabel ? 'correct' : 'chosen-wrong') : ''
                  }`.trim()}
                >
                  <span className="key">{L}</span>
                  <span className="body">
                    {question.options[L]}
                    {isDistractor ? (
                      <span className="why" style={{ display: 'block', borderTopStyle: 'solid' }}>
                        <b>Which explanation fits {L}?</b>
                        <span className="seg" style={{ marginTop: 7 }}>
                          {explanations.map((e) => (
                            <button
                              key={e.label}
                              className={mine === e.label ? 'on' : ''}
                              disabled={!!result}
                              onClick={() => setMapping((m) => ({ ...m, [L]: e.label }))}
                            >
                              {e.label}
                            </button>
                          ))}
                        </span>
                        {result ? (
                          <span style={{ display: 'block', marginTop: 7 }}>
                            {mine === truthLabel ? (
                              <span className="chip good">correct</span>
                            ) : (
                              <span className="chip bad">should be {truthLabel}</span>
                            )}
                          </span>
                        ) : null}
                      </span>
                    ) : null}
                  </span>
                </div>
              )
            })}
          </div>

          <Section>The three reasons, scrambled</Section>
          <Card>
            <div className="list">
              {explanations.map((e) => (
                <div className="list-row" key={e.label}>
                  <span
                    className="key"
                    style={{
                      width: 26, height: 26, borderRadius: 6, background: 'var(--raised)',
                      border: '1px solid var(--line)', display: 'grid', placeItems: 'center',
                      fontFamily: 'var(--mono)', fontSize: 12.5, flex: '0 0 26px',
                    }}
                  >
                    {e.label}
                  </span>
                  <div className="grow" style={{ fontSize: 13.5, color: 'var(--text-dim)' }}>
                    {e.text}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {!result ? (
            <div className="runner-foot">
              <button className="btn primary" onClick={check} disabled={!ready}>Check</button>
              <span className="kbd-hint">assign a letter to every wrong option</span>
            </div>
          ) : (
            <Card>
              <div className="score-hero">
                <div className={`big ${result.correct ? 'good' : ''}`.trim()}>
                  {result.matched}/{result.total}
                </div>
                <div className="dim">matched correctly</div>
              </div>
              {result.why_correct ? (
                <p className="sub" style={{ marginTop: 12 }}>
                  <b style={{ color: 'var(--good)' }}>Why {question.answer} is right</b> —{' '}
                  {result.why_correct}
                </p>
              ) : null}
              <div className="btn-row" style={{ marginTop: 12 }}>
                <button
                  className="btn primary"
                  autoFocus
                  onClick={() => {
                    if (index + 1 >= data.questions.length) setDone(true)
                    else setIndex((i) => i + 1)
                  }}
                >
                  {index + 1 >= data.questions.length ? 'Finish' : 'Next'}
                </button>
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  )
}
