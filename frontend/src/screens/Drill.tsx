/**
 * Drill — the core of the system; everything else supports it.
 *
 * Keyboard first: A-D or 1-4 answers, Enter advances, Esc leaves. The mouse
 * works, but the intended loop is hands on the keyboard, and the whole runner
 * is built so a session can be completed without touching a pointer.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import type {
  Confidence, Difficulty, DrillAvailability, DrillMode, DrillStart,
  DrillStartParams, Letter, Reveal,
} from '../api/types'
import { DIFFICULTY_BANDS } from '../api/types'
import { ConfidencePicker, CONFIDENCE_META } from '../ui/ConfidencePicker'
import { LETTERS, pct } from '../lib/format'
import { useKeys } from '../lib/hooks'
import { Callout, Card, Field, Loading, Seg } from '../ui/primitives'
import { OptionList, QuestionMeta, RuleNote } from '../ui/QuestionView'

const MODES: { value: DrillMode; label: string }[] = [
  { value: 'smart', label: 'Smart' },
  { value: 'due', label: 'Due for review' },
  { value: 'weakest', label: 'Weakest first' },
  { value: 'principle', label: 'Weak decision rules' },
  { value: 'random', label: 'Random' },
]

const MODE_BLURB: Record<DrillMode, string> = {
  smart: 'Spaced-repetition-lite: mixes questions you are due to forget with ones you have never seen.',
  due: 'Only questions the scheduler thinks are decaying. Shortest path to holding what you already learned.',
  weakest: 'Your lowest-accuracy material first. Blunt, and useful right before an exam.',
  principle: 'Selects across the decision rules you are weakest on, regardless of topic.',
  random: 'Uniform sample of the bank. No scheduling, no targeting.',
  costumes: 'One decision rule, shown across every domain it appears in.',
}

// Mirrors difficulty.CAVEAT server-side; shown before the first preview lands.
const DIFFICULTY_CAVEAT = 'Author-assigned, not yet checked against your results'

const DIFFICULTY_OPTIONS: { value: Difficulty; label: string }[] = [
  { value: '', label: 'Any' },
  { value: 'easy', label: 'Easy' },
  { value: 'medium', label: 'Medium' },
  { value: 'hard', label: 'Hard' },
  { value: 'expert', label: 'Expert' },
  { value: 'ramp', label: 'Ramp' },
]

/**
 * Prefill from the query string, so a recommendation on the Next Session
 * screen arrives here as a configured drill rather than a blank form. Without
 * this the recommendation is decorative: it names a rule, then drops you on
 * an empty setup and asks you to find it yourself.
 *
 * Only the initial state is seeded. The controls stay authoritative after
 * that - a link sets the starting point, it does not lock anything.
 */
function useQueryDefaults() {
  const { search } = useLocation()
  const q = new URLSearchParams(search)
  const mode = q.get('mode') as DrillMode | null
  const count = Number(q.get('n'))
  return {
    search,
    mode: mode && MODE_BLURB[mode] ? mode : null,
    topic: q.get('topic') ?? '',
    domain: q.get('domain') ?? '',
    rule: q.get('principle') ?? '',
    n: Number.isFinite(count) && count > 0 ? Math.min(count, 150) : null,
  }
}

export function DrillSetup() {
  const { boot } = useApp()
  const nav = useNavigate()
  const seed = useQueryDefaults()
  const [mode, setMode] = useState<DrillMode>(seed.mode ?? 'smart')
  const [domain, setDomain] = useState(seed.domain)
  const [topic, setTopic] = useState(seed.topic)
  const [n, setN] = useState(seed.n ?? 20)
  const [rule, setRule] = useState(seed.rule)
  const [difficulty, setDifficulty] = useState<Difficulty>('')
  const [avail, setAvail] = useState<DrillAvailability | null>(null)

  /*
   * Re-seed when the query changes, not only on mount. React Router keeps this
   * component mounted across `/drill?a` -> `/drill?b`, so the initialisers
   * above never run again: go back from one recommendation and click the next
   * and you would silently get the first one's settings. Skipped when there is
   * no query at all, so navigating to a bare /drill does not wipe the form.
   */
  useEffect(() => {
    if (!seed.search) return
    setMode(seed.mode ?? 'smart')
    setDomain(seed.domain)
    setTopic(seed.topic)
    setN(seed.n ?? 20)
    setRule(seed.rule)
  }, [seed.search])

  /*
   * Availability is fetched as the filters change, so an empty or short pool is
   * visible before the learner commits. A fifth of topic-plus-difficulty
   * combinations return nothing at all, which makes this the normal path rather
   * than an error path. Debounced because the topic box fires on every keystroke.
   */
  useEffect(() => {
    if (!difficulty) {
      setAvail(null)
      return
    }
    let live = true
    const timer = window.setTimeout(() => {
      api.drillPreview({ mode, n, domain, topic: topic.trim(), difficulty })
        .then((data) => { if (live) setAvail(data) })
        .catch(() => { if (live) setAvail(null) })
    }, 200)
    return () => { live = false; window.clearTimeout(timer) }
  }, [difficulty, domain, topic, n, mode])

  const blocked = !!avail?.empty

  return (
    <div className="wrap narrow">
      <div className="page-head">
        <h1>Drill</h1>
        <p>
          Full scenario questions with the reasoning behind every option. This is the core of
          the system; everything else supports it.
        </p>
      </div>

      <Card>
        <Field label="How questions are chosen">
          <Seg value={mode} options={MODES} onChange={setMode} />
        </Field>
        <p className="sub" style={{ marginTop: -4 }}>{MODE_BLURB[mode]}</p>

        <div className="grid c3">
          <Field label="Domain">
            <select value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">All domains</option>
              {boot.domains.map((d) => (
                <option key={d.id} value={d.id}>
                  D{d.id} — {d.name} ({d.weight}%)
                </option>
              ))}
            </select>
          </Field>
          <Field label="Topic contains">
            <input
              type="text"
              value={topic}
              placeholder="e.g. encryption"
              onChange={(e) => setTopic(e.target.value)}
            />
          </Field>
          <Field label="How many">
            <select value={n} onChange={(e) => setN(Number(e.target.value))}>
              {[5, 10, 15, 20, 30, 50].map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Difficulty">
          <Seg value={difficulty} options={DIFFICULTY_OPTIONS}
               onChange={setDifficulty} />
        </Field>
        {difficulty ? (
          <p className="sub" style={{ marginTop: -4 }}>
            {difficulty === 'ramp'
              ? 'Keeps whatever the scheduler picked and orders it easiest first.'
              : 'Strict: only ' + difficulty + ' questions, never topped up from '
                + 'another band.'}{' '}
            <span className="dim">{avail?.caveat ?? DIFFICULTY_CAVEAT}</span>
          </p>
        ) : null}

        {avail && difficulty && difficulty !== 'ramp' ? (
          <div style={{ marginBottom: 14 }}>
            <Callout kind={avail.empty ? 'bad' : avail.short ? 'warn' : 'info'}>
              <p>{avail.message}</p>
              {avail.empty ? (
                <p>
                  This combination has{' '}
                  {DIFFICULTY_BANDS.map((b, i) => (
                    <span key={b}>
                      {i ? ', ' : ''}
                      <b>{avail.counts[b] ?? 0}</b> {b}
                    </span>
                  ))}
                  . Pick another band or widen the filters.
                </p>
              ) : null}
              {avail.due_suppressed ? (
                <p>
                  {avail.due_suppressed} question{avail.due_suppressed === 1 ? '' : 's'}{' '}
                  due for review {avail.due_suppressed === 1 ? 'is' : 'are'} not{' '}
                  {difficulty} and will be held back.
                </p>
              ) : null}
            </Callout>
          </div>
        ) : null}

        <div className="btn-row">
          <button
            className="btn primary"
            disabled={blocked}
            onClick={() =>
              nav('/drill/run', {
                state: {
                  mode, n, domain, topic: topic.trim(), difficulty,
                } satisfies DrillStartParams,
              })
            }
          >
            {blocked ? 'Nothing to drill' : 'Start drill'}
          </button>
          <span className="dim" style={{ fontSize: 12.5 }}>
            Answer with <kbd>A</kbd>–<kbd>D</kbd> or <kbd>1</kbd>–<kbd>4</kbd>, then <kbd>Enter</kbd>
          </span>
        </div>
      </Card>

      <Card>
        <h3>Same rule, five costumes</h3>
        <p className="sub">
          One decision rule shown across every domain it appears in. The surface changes
          completely; the reasoning does not.
        </p>
        <Field label="Rule">
          <select value={rule} onChange={(e) => setRule(e.target.value)}>
            <option value="">Your weakest rule</option>
            {boot.principles.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </Field>
        <button
          className="btn"
          onClick={() =>
            nav('/drill/run', { state: { mode: 'costumes', principle: rule } })
          }
        >
          Run costumes
        </button>
        <p className="sub" style={{ margin: '12px 0 0' }}>
          Costumes is not a short-form game — these are full questions answered normally, so they
          count as real evidence.
        </p>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------- runner

interface Progress {
  index: number
  answered: number
  right: number
}

export function DrillRunner() {
  const { toast } = useApp()
  const nav = useNavigate()
  const location = useLocation()
  const params = (location.state ?? { mode: 'smart', n: 20 }) as DrillStartParams

  const [set, setSet] = useState<DrillStart | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<Progress>({ index: 0, answered: 0, right: 0 })
  const [reveal, setReveal] = useState<Reveal | null>(null)
  const [chosen, setChosen] = useState<Letter | null>(null)
  const [rated, setRated] = useState<Confidence>('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)

  const questionStart = useRef(Date.now())
  const sessionStart = useRef(Date.now())
  const chosenRef = useRef<Letter | null>(null)
  const nextRef = useRef<HTMLButtonElement | null>(null)
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    api.drillStart(params).then(
      (data) => {
        setSet(data)
        questionStart.current = Date.now()
        sessionStart.current = Date.now()
      },
      (err: unknown) => setError(err instanceof Error ? err.message : String(err)),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const question = set?.questions[progress.index] ?? null

  /**
   * Two keystrokes, one action. Picking a letter only *selects* it; the answer
   * is not submitted until confidence is given, so the rating is always
   * recorded before the learner can see whether they were right. Rating after
   * the reveal would be hindsight and worth nothing.
   */
  const select = useCallback(
    (letter: Letter) => {
      if (!set || !question || reveal || pending) return
      // Mirrored into a ref as well as state: the confidence keystroke can
      // arrive in the same tick as the letter, before React has re-rendered,
      // and reading stale state there would silently drop the rating.
      chosenRef.current = letter
      setChosen(letter)
    },
    [set, question, reveal, pending],
  )

  const submit = useCallback(
    async (letter: Letter, confidence: Exclude<Confidence, ''>) => {
      if (!set || !question || reveal || pending) return
      setPending(true)
      try {
        const res = await api.drillAnswer({
          question_id: question.id,
          chosen: letter,
          session: set.session,
          mode: set.mode,
          seconds: (Date.now() - questionStart.current) / 1000,
          confidence,
        })
        setReveal(res)
        setRated(confidence)
        setProgress((p) => ({
          ...p,
          answered: p.answered + 1,
          right: p.right + (res.correct ? 1 : 0),
        }))
      } catch (err) {
        toast(err instanceof Error ? err.message : String(err), true)
      } finally {
        setPending(false)
      }
    },
    [set, question, reveal, pending, toast],
  )

  const next = useCallback(() => {
    if (!set) return
    if (progress.index + 1 >= set.questions.length) {
      setDone(true)
      return
    }
    setReveal(null)
    setChosen(null)
    chosenRef.current = null
    setRated('')
    setProgress((p) => ({ ...p, index: p.index + 1 }))
    questionStart.current = Date.now()
  }, [set, progress.index])

  useEffect(() => {
    if (reveal) nextRef.current?.focus()
  }, [reveal])

  useKeys(
    (ev) => {
      if (done) return
      if (ev.key === 'Escape') {
        ev.preventDefault()
        nav('/')
        return
      }
      if (!reveal) {
        // A-D selects. 1-3 then rates and submits. Digits are confidence here,
        // not option numbers: the answer key is always a letter in this bank,
        // and overloading 1-4 would make the second keystroke ambiguous.
        const byLetter = LETTERS.indexOf(ev.key.toUpperCase() as Letter)
        if (byLetter >= 0) {
          ev.preventDefault()
          select(LETTERS[byLetter])
          return
        }
        const level = CONFIDENCE_META.find((c) => c.key === ev.key)
        if (level && chosenRef.current) {
          ev.preventDefault()
          void submit(chosenRef.current, level.level)
        }
      } else if (ev.key === 'Enter' || ev.key === ' ') {
        ev.preventDefault()
        next()
      }
    },
    !done,
  )

  if (error) {
    return (
      <div className="wrap narrow">
        <Callout kind="bad">
          <p><b>Could not start that drill.</b> {error}</p>
          <p><Link className="btn" to="/drill" style={{ marginTop: 8 }}>Back to drill setup</Link></p>
        </Callout>
      </div>
    )
  }
  if (!set || !question) return <div className="wrap"><Loading what="Building your set…" /></div>

  if (done) {
    const minutes = (Date.now() - sessionStart.current) / 60000
    const acc = progress.answered ? progress.right / progress.answered : 0
    return (
      <div className="wrap narrow">
        <div className="page-head"><h1>Session complete</h1></div>
        <Card>
          <div className="score-hero">
            <div className={`big ${acc >= 0.7 ? 'good' : acc < 0.5 ? 'bad' : ''}`.trim()}>
              {progress.right}/{progress.answered}
            </div>
            <div>
              <div style={{ fontSize: 19 }}>{pct(acc)}</div>
              <div className="dim" style={{ fontSize: 13 }}>
                {minutes.toFixed(1)} min ·{' '}
                {progress.answered ? ((minutes * 60) / progress.answered).toFixed(0) : '0'}s per question
              </div>
            </div>
          </div>
          <p className="sub" style={{ margin: '14px 0 0' }}>
            A single session is a small sample — this figure carries no interval on purpose,
            because it is a session tally rather than a claim about what you know. The dashboard
            is where it turns into evidence.
          </p>
        </Card>
        <div className="btn-row" style={{ marginTop: 16 }}>
          <Link className="btn primary" to="/drill">Another drill</Link>
          <Link className="btn" to="/">Dashboard</Link>
          <Link className="btn" to="/rules">See what the misses have in common</Link>
        </div>
      </div>
    )
  }

  return (
    <>
      <div className="runner-top">
        <div className="progress">
          <span style={{ width: `${(progress.index / set.questions.length) * 100}%` }} />
        </div>
        <div className="meta">{progress.index + 1} of {set.questions.length}</div>
        <div className="meta">
          {progress.answered ? `${progress.right}/${progress.answered} correct` : ''}
        </div>
        <div className="grow" />
        <button className="btn ghost" onClick={() => (progress.answered ? setDone(true) : nav('/'))}>
          End session
        </button>
      </div>

      <div className="wrap">
        {set.header ? (
          <div style={{ marginBottom: 18 }}>
            <Callout kind="info"><p><b>{set.header}</b></p></Callout>
          </div>
        ) : null}

        {/* The reorder-only ramp cannot invent a spread that the scheduler's
            selection does not contain. Say so rather than claiming a ramp. */}
        {progress.index === 0 && set.difficulty === 'ramp' && set.ramp_bands < 2 ? (
          <div style={{ marginBottom: 18 }}>
            <Callout>
              <p>
                Every question the scheduler picked is the same difficulty, so there
                is no ramp today. The set is unchanged.
              </p>
            </Callout>
          </div>
        ) : null}

        <div className="qcard">
          <QuestionMeta question={question} />
          <p className="stem">{question.stem}</p>

          <OptionList
            question={question}
            reveal={reveal}
            chosen={chosen}
            onChoose={select}
            pending={pending}
          />

          {!reveal && chosen ? (
            <ConfidencePicker
              value={rated}
              onPick={(level) => void submit(chosen, level)}
              disabled={pending}
            />
          ) : null}

          {reveal ? (
            <>
              {rated ? (
                <div className="rated-note">
                  You rated this <b>{rated}</b> before seeing the answer
                  {reveal.correct
                    ? rated === 'confident' ? ' — and you were right.' : ' — and got it right.'
                    : rated === 'confident'
                      ? ' — and were wrong. This is the quadrant that costs marks.'
                      : ' — and were wrong, which you half expected.'}
                </div>
              ) : null}
              {reveal.principle ? <RuleNote principle={reveal.principle} /> : null}
              <div className="runner-foot">
                <button className="btn primary" ref={nextRef} onClick={next}>
                  {progress.index + 1 >= set.questions.length ? 'Finish' : 'Next question'}
                </button>
                <span className="kbd-hint">press <kbd>Enter</kbd></span>
              </div>
            </>
          ) : (
            <div className="runner-foot">
              <span className="kbd-hint">
                {chosen
                  ? <><kbd>1</kbd><kbd>2</kbd><kbd>3</kbd> to rate and submit</>
                  : <><kbd>A</kbd>–<kbd>D</kbd> to choose, then <kbd>1</kbd>–<kbd>3</kbd></>}
                {' · '}<kbd>Esc</kbd> to exit
              </span>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
