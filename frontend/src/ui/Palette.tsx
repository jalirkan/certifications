/**
 * Command palette — Ctrl-K / ⌘K.
 *
 * The app is already keyboard-first inside a drill: A–D answers, Enter
 * advances, Esc leaves. Everything *between* sessions was mouse-only, which is
 * the part that makes it feel like a website rather than an instrument. This
 * closes that: jump to any screen, start any drill configuration, open any
 * case, resume a sitting, check the bank.
 *
 * Drill configurations are real, not links to a blank form. They work because
 * the Drill setup screen reads its query string, so `#/drill?mode=costumes&
 * principle=evidence-quality` arrives configured — the same mechanism the Next
 * Session recommendations use.
 *
 * Deliberate choices:
 *
 * - **Substring match, not fuzzy.** With around forty commands, subsequence
 *   matching mostly buys surprising results: typing "case" would rank
 *   "Calibration" alongside the cases because c-a-s-e appears scattered
 *   through it. Every command also carries keywords, so "wrong", "missed" and
 *   "review" all find the due-questions drill without anyone guessing the
 *   exact label.
 * - **No recents, no frecency, no scoring.** A stable list you can learn beats
 *   one that reorders itself under you, and a palette that ranks by how often
 *   you have used something is a gamification surface by another name.
 * - **Focus is restored on close.** Opening and dismissing the palette must
 *   leave the keyboard exactly where it was, or it costs more than it saves.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../app/AppProvider'
import { api } from '../api/client'
import type { CaseListEntry } from '../api/types'

export interface Command {
  id: string
  label: string
  hint?: string
  group: string
  keywords?: string
  run: () => void | Promise<void>
}

const GROUP_ORDER = ['Go', 'Drill', 'Cases', 'Bank', 'Profile']

function useCases(open: boolean): CaseListEntry[] {
  const [cases, setCases] = useState<CaseListEntry[]>([])
  useEffect(() => {
    if (!open || cases.length) return
    let live = true
    api.caseList().then((d) => { if (live) setCases(d.cases) }).catch(() => {})
    return () => { live = false }
  }, [open, cases.length])
  return cases
}

export function Palette() {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [cursor, setCursor] = useState(0)
  const [note, setNote] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const restoreTo = useRef<Element | null>(null)
  const navigate = useNavigate()
  const { boot, profile, switchProfile } = useApp()
  const cases = useCases(open)

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'k') {
        ev.preventDefault()
        setOpen((was) => {
          if (!was) restoreTo.current = document.activeElement
          return !was
        })
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) {
      setQuery('')
      setCursor(0)
      setNote(null)
      // Directly, not inside requestAnimationFrame. The component renders null
      // while closed, so the input mounts on the render that opens it and the
      // ref is already set by the time this effect runs — and rAF is throttled
      // in a backgrounded tab, which silently skipped the focus entirely.
      inputRef.current?.focus()
    } else if (restoreTo.current instanceof HTMLElement) {
      restoreTo.current.focus()
      restoreTo.current = null
    }
  }, [open])

  const commands = useMemo<Command[]>(() => {
    const go = (to: string) => () => { navigate(to); setOpen(false) }
    const list: Command[] = [
      { id: 'go-next', group: 'Go', label: 'Next session',
        hint: 'what to study, with the evidence', keywords: 'recommend plan what should i do',
        run: go('/next') },
      { id: 'go-dash', group: 'Go', label: 'Dashboard', keywords: 'home overview stats',
        run: go('/') },
      { id: 'go-exam', group: 'Go', label: 'Mock exam', keywords: 'timed 150 sitting',
        run: go('/exam') },
      { id: 'go-cases', group: 'Go', label: 'Cases', keywords: 'branching scenario',
        run: go('/cases') },
      { id: 'go-games', group: 'Go', label: 'Short form', keywords: 'cold read autopsy game',
        run: go('/games') },
      { id: 'go-rules', group: 'Go', label: 'Decision rules',
        keywords: 'principles transfer axis', run: go('/rules') },
      { id: 'go-card', group: 'Go', label: 'Study card', keywords: 'print rules reference',
        run: go('/rules/card') },
      { id: 'go-cal', group: 'Go', label: 'Calibration',
        keywords: 'confidence overconfident dangerous quadrant', run: go('/calibration') },
      { id: 'go-det', group: 'Go', label: 'Detection',
        keywords: 'does this tool work report card evidence', run: go('/detection') },
      { id: 'go-bank', group: 'Go', label: 'Question bank',
        keywords: 'items coverage pairs confusable', run: go('/bank') },

      { id: 'd-smart', group: 'Drill', label: 'Drill 20 — smart',
        hint: 'spaced repetition over the whole bank', keywords: 'default start study',
        run: go('/drill?mode=smart&n=20') },
      { id: 'd-due', group: 'Drill', label: 'Drill 20 — due for review',
        hint: 'only what the scheduler thinks is decaying', keywords: 'forget review decay',
        run: go('/drill?mode=due&n=20') },
      { id: 'd-weak', group: 'Drill', label: 'Drill 20 — weakest first',
        hint: 'lowest accuracy material', keywords: 'wrong missed bad worst review',
        run: go('/drill?mode=weakest&n=20') },
      { id: 'd-rule', group: 'Drill', label: 'Drill 20 — weak decision rules',
        hint: 'across topics, by reasoning habit', keywords: 'principle transfer',
        run: go('/drill?mode=principle&n=20') },
      { id: 'd-random', group: 'Drill', label: 'Drill 20 — random',
        hint: 'uniform sample, no scheduling', keywords: 'shuffle any',
        run: go('/drill?mode=random&n=20') },
      { id: 'd-quick', group: 'Drill', label: 'Drill 5 — quick',
        hint: 'five minutes', keywords: 'short fast small',
        run: go('/drill?mode=smart&n=5') },
      { id: 'd-50', group: 'Drill', label: 'Drill 50 — smart',
        hint: 'a long session', keywords: 'big long many',
        run: go('/drill?mode=smart&n=50') },
      { id: 'd-setup', group: 'Drill', label: 'Drill — configure it yourself',
        keywords: 'custom filter topic domain difficulty', run: go('/drill') },
    ]

    for (const d of boot.domains) {
      list.push({
        id: `d-dom-${d.id}`, group: 'Drill',
        label: `Drill 20 — Domain ${d.id}`,
        hint: d.name,
        keywords: `d${d.id} ${d.name}`,
        run: go(`/drill?domain=${d.id}&n=20`),
      })
    }

    for (const p of boot.principles) {
      list.push({
        id: `d-rule-${p.id}`, group: 'Drill',
        label: `Costumes — ${p.name}`,
        hint: 'one rule, across every domain it appears in',
        keywords: `${p.id} ${p.statement} principle rule costume`,
        run: go(`/drill?mode=costumes&principle=${encodeURIComponent(p.id)}&n=10`),
      })
    }

    for (const c of cases) {
      list.push({
        id: `case-${c.id}`, group: 'Cases',
        label: c.open_session ? `Resume — ${c.title}` : `Play — ${c.title}`,
        hint: c.open_session
          ? `${c.open_decisions} decisions in`
          : `D${c.domain}${c.section} · about ${c.minutes} min`,
        keywords: `${c.id} ${c.topics.join(' ')}`,
        run: c.open_session
          ? go(`/cases/run/${c.open_session}`)
          : go(`/cases?case=${encodeURIComponent(c.id)}`),
      })
    }

    list.push({
      id: 'bank-validate', group: 'Bank', label: 'Validate the question bank',
      hint: 'ids, answer keys, topic tags, rule and pair references',
      keywords: 'check integrity errors warnings lint',
      run: async () => {
        setNote('Checking…')
        try {
          const v = await api.validate()
          setNote(
            v.ok
              ? `Clean — ${v.questions} questions, ${v.rules} rules, ${v.pairs} pairs, ${v.cases} cases.`
                + (v.warnings.length ? ` ${v.warnings.length} warning(s): ${v.warnings[0]}` : '')
              : `${v.errors.length} error(s). First: ${v.errors[0]}`,
          )
        } catch (err) {
          setNote(err instanceof Error ? err.message : 'Validation failed.')
        }
      },
    })

    for (const name of boot.profiles) {
      if (name === profile) continue
      list.push({
        id: `p-${name}`, group: 'Profile', label: `Switch to profile — ${name}`,
        keywords: 'profile user learner switch',
        run: () => { switchProfile(name); setOpen(false) },
      })
    }

    return list
  }, [boot, cases, profile, navigate, switchProfile])

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const hit = needle
      ? commands.filter((c) =>
          `${c.label} ${c.hint ?? ''} ${c.keywords ?? ''}`.toLowerCase().includes(needle))
      : commands
    return [...hit].sort(
      (a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group))
  }, [commands, query])

  useEffect(() => { setCursor(0) }, [query])

  useEffect(() => {
    listRef.current
      ?.querySelector('[data-active="true"]')
      ?.scrollIntoView({ block: 'nearest' })
  }, [cursor, matches.length])

  if (!open) return null

  const onKeyDown = (ev: React.KeyboardEvent) => {
    if (ev.key === 'Escape') { ev.preventDefault(); setOpen(false) }
    else if (ev.key === 'ArrowDown') {
      ev.preventDefault(); setCursor((c) => Math.min(c + 1, matches.length - 1))
    } else if (ev.key === 'ArrowUp') {
      ev.preventDefault(); setCursor((c) => Math.max(c - 1, 0))
    } else if (ev.key === 'Enter') {
      ev.preventDefault(); void matches[cursor]?.run()
    }
  }

  let lastGroup = ''

  return (
    <div className="palette-scrim" onMouseDown={() => setOpen(false)}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette"
           onMouseDown={(ev) => ev.stopPropagation()}>
        <input
          ref={inputRef}
          className="palette-input"
          value={query}
          placeholder="Jump to a screen, start a drill, open a case…"
          aria-label="Command"
          aria-expanded="true"
          aria-controls="palette-list"
          aria-activedescendant={matches[cursor] ? `pal-${matches[cursor].id}` : undefined}
          onChange={(ev) => setQuery(ev.target.value)}
          onKeyDown={onKeyDown} />

        {note ? <div className="palette-note">{note}</div> : null}

        <div className="palette-list" id="palette-list" role="listbox" ref={listRef}>
          {matches.length === 0 ? (
            <div className="palette-empty">Nothing matches “{query}”.</div>
          ) : matches.map((c, i) => {
            const header = c.group !== lastGroup ? c.group : null
            lastGroup = c.group
            return (
              <div key={c.id}>
                {header ? <div className="palette-group">{header}</div> : null}
                <div id={`pal-${c.id}`} role="option" aria-selected={i === cursor}
                     data-active={i === cursor}
                     className={`palette-row${i === cursor ? ' on' : ''}`}
                     onMouseMove={() => setCursor(i)}
                     onClick={() => void c.run()}>
                  <span className="t">{c.label}</span>
                  {c.hint ? <span className="s">{c.hint}</span> : null}
                </div>
              </div>
            )
          })}
        </div>

        <div className="palette-foot">
          <kbd>↑</kbd><kbd>↓</kbd> move · <kbd>Enter</kbd> run · <kbd>Esc</kbd> close
        </div>
      </div>
    </div>
  )
}
