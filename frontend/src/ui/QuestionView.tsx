/**
 * Question rendering, shared by the drill runner and exam review.
 *
 * The load-bearing detail: when a question is revealed, each explanation is
 * attached to the option it explains, rather than listed underneath. In the
 * terminal you have to map "why B is wrong" back to option B yourself; here the
 * reasoning sits inside the thing it is reasoning about. That is the main thing
 * this front end can do that the CLI cannot.
 *
 * `reveal` is null until the user commits. There is no code path that renders
 * an answer key before the server has sent one.
 */

import type { Letter, PrincipleRef, Question, Reveal } from '../api/types'
import { LETTERS } from '../lib/format'

export function QuestionMeta({ question, extra }: { question: Question; extra?: React.ReactNode }) {
  return (
    <div className="qmeta">
      <span className="chip mono">{question.tag}</span>
      <span className="chip">{question.topic}</span>
      {question.difficulty ? <span className="chip">{question.difficulty}</span> : null}
      {extra}
    </div>
  )
}

export function OptionList({
  question, reveal, chosen, onChoose, pending,
}: {
  question: Question
  reveal: Reveal | null
  chosen: Letter | null
  onChoose?: (letter: Letter) => void
  pending?: boolean
}) {
  const locked = reveal != null || pending || !onChoose

  return (
    <div className="options">
      {LETTERS.map((L) => {
        const text = question.options[L] ?? ''
        let cls = 'opt'
        if (reveal) {
          if (L === reveal.answer) cls += ' correct'
          else if (L === reveal.chosen) cls += ' chosen-wrong'
          else cls += ' dimmed'
        } else if (chosen === L) {
          cls += ' selected'
        }
        if (locked) cls += ' static'

        const why = reveal
          ? L === reveal.answer
            ? reveal.why_correct
            : reveal.why_wrong[L]
          : null

        const content = (
          <>
            <span className="key">{L}</span>
            <span className="body">
              {text}
              {why ? (
                <span
                  className={`why ${L === reveal?.answer ? 'good' : 'bad'}`}
                  style={{ display: 'block' }}
                >
                  <b>{L === reveal?.answer ? 'Why this is right' : 'Why this is wrong'}</b> — {why}
                </span>
              ) : null}
            </span>
          </>
        )

        return locked ? (
          <div key={L} className={cls}>{content}</div>
        ) : (
          <button
            key={L}
            className={cls}
            onClick={() => onChoose?.(L)}
            aria-label={`Option ${L}: ${text}`}
          >
            {content}
          </button>
        )
      })}
    </div>
  )
}

export function RuleNote({ principle, showScope = true }: {
  principle: PrincipleRef
  showScope?: boolean
}) {
  return (
    <div className="rule-note">
      <div className="kicker">The rule that decides this</div>
      <h4>{principle.name}</h4>
      <p>{principle.statement}</p>
      {principle.misapplication ? (
        <div className="trap">
          <b>Trap</b> — {principle.misapplication}
        </div>
      ) : null}
      {showScope && principle.scope ? (
        <div className="scope">
          <b>Scope</b> — {principle.scope}
        </div>
      ) : null}
    </div>
  )
}
