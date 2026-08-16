/**
 * Question bank — item analysis and the confusable-pair reference.
 *
 * This page is about the *questions*, not about the user. A flag here means the
 * item's own statistics suggest it is badly written: everyone gets it wrong, or
 * strong answerers get it wrong more often than weak ones. Keeping that
 * distinction visible is what stops item analysis reading as another verdict on
 * the learner.
 */

import { useState } from 'react'
import { api } from '../api/client'
import { useApp } from '../app/AppProvider'
import { DifficultySpread } from '../charts/DifficultySpread'
import { useAsync } from '../lib/hooks'
import { num, plural } from '../lib/format'
import { Callout, Card, ErrorNote, Loading, Section, Stat } from '../ui/primitives'

export function Bank() {
  const { boot, epoch } = useApp()
  const items = useAsync(() => api.items(5), [epoch])
  const [filter, setFilter] = useState('')

  const pairs = boot.pairs.filter((p) => {
    if (!filter.trim()) return true
    const needle = filter.toLowerCase()
    return (
      p.label.toLowerCase().includes(needle) ||
      p.discriminator.toLowerCase().includes(needle) ||
      p.terms.some((t) => t.toLowerCase().includes(needle))
    )
  })
  const uncovered = boot.pairs.filter((p) => !p.questions).length

  return (
    <div className="wrap">
      <div className="page-head">
        <h1>Question bank</h1>
        <p>
          This page is about the <em>questions</em>, not about you. It surfaces items whose own
          statistics suggest they are badly written.
        </p>
      </div>

      {items.loading ? (
        <Loading />
      ) : items.error || !items.data ? (
        <ErrorNote message={items.error ?? 'No data'} onRetry={items.reload} />
      ) : (
        <>
          <div className="grid c4">
            <Stat
              label="Questions"
              value={num(items.data.total)}
              foot={`${items.data.served} served, ${items.data.never_served} untouched`}
            />
            <Stat
              label="With statistics"
              value={num(items.data.with_stats)}
              foot="enough attempts to judge"
            />
            <Stat
              label="Mean difficulty"
              value={items.data.mean_p == null ? '—' : items.data.mean_p.toFixed(2)}
              foot="proportion correct"
            />
            {/*
              An empty stat should say why it is empty. Discrimination needs
              about twenty attempts on one question, and one learner's answers
              spread over the whole bank rarely put that many anywhere - so
              this reads "—" almost always, and "higher is better" underneath a
              permanent dash tells the reader nothing. DETECTION.md check 4.
            */}
            <Stat
              label="Mean discrimination"
              value={
                items.data.mean_discrimination == null
                  ? '—'
                  : `${items.data.mean_discrimination >= 0 ? '+' : ''}${items.data.mean_discrimination.toFixed(2)}`
              }
              foot={
                items.data.with_discrimination
                  ? `higher is better · ${items.data.with_discrimination} of ${items.data.with_stats} items measurable`
                  : 'not measurable yet — needs ~20 answers on one question'
              }
            />
          </div>

          <Section>Difficulty spread</Section>
          <Card>
            <DifficultySpread
              spread={items.data.spread}
              withStats={items.data.with_stats}
            />
          </Card>

          <Section>Questions worth rewriting</Section>
          {items.data.suspect.length ? (
            <Card>
              <p className="sub">
                These flags describe the question, not you — an item everyone gets wrong, or one
                where strong answerers do worse than weak ones, is usually badly written. The IDs
                below are what to hand over when rewriting them.
              </p>
              <div className="list">
                {items.data.suspect.map((s) => (
                  <div className="list-row" key={s.id}>
                    <span className="mono">{s.id}</span>
                    <div className="grow"><div className="s">{s.topic}</div></div>
                    <span className="chip mono">
                      p={s.p == null ? '—' : s.p.toFixed(2)}
                    </span>
                    <span className="chip mono">{s.attempts}n</span>
                    {s.flags.map((f) => (
                      <span className="chip warn" key={f}>{f}</span>
                    ))}
                  </div>
                ))}
              </div>
            </Card>
          ) : (
            <Callout kind="info">
              <p>
                Not enough attempts yet to flag any questions. This fills in as you drill — item
                analysis needs a handful of answers per question before it can say anything.
              </p>
            </Callout>
          )}
        </>
      )}

      <Section hint={`${boot.pairs.length} documented`}>Confusable pairs</Section>
      <Card>
        <p className="sub">
          The discriminator is what separates them; the trap is how the exam exploits it.
          {uncovered
            ? ` ${uncovered} ${plural(uncovered, 'pair')} still ${plural(uncovered, 'has', 'have')} no question testing it.`
            : ''}
        </p>
        <div className="field">
          <input
            type="text"
            value={filter}
            placeholder="Filter pairs — e.g. validation, encryption"
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter confusable pairs"
          />
        </div>
        {pairs.map((p) => (
          <details className="pair" key={p.id}>
            <summary>
              {p.label}
              <span className="chip">D{p.domain}</span>
              {p.questions ? (
                <span className="chip">{p.questions} q</span>
              ) : (
                <span className="chip warn">no coverage</span>
              )}
            </summary>
            <p>{p.discriminator}</p>
            <p className="trap"><b>Trap</b> — {p.trap}</p>
          </details>
        ))}
        {!pairs.length ? <p className="sub">Nothing matches that filter.</p> : null}
      </Card>
    </div>
  )
}
