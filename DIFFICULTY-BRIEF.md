# Difficulty selection — handoff brief

> **Status: built 2026-07-31.** `drillkit/difficulty.py` (175 lines) and
> `tests/test_difficulty.py` (34 tests). Every item in §6 is on disk.
>
> - `--difficulty` on `python drill.py drill`, and the matching control in the web Drill screen;
>   14 references in `drillkit/webapi.py` carry it through the API.
> - Strict filtering applied before the scheduler orders what survives, with `availability()`
>   reporting the count and the reason *before* the session starts.
> - Ramp mode built the reorder-only way argued for in §4 — `scheduler.select` picks, the ramp
>   sorts — with `ramp_spread()` disclosing the days when the draw is all one band.
> - `difficulty.CAVEAT` is mirrored on every surface, so the labels always read as author-assigned.
>
> **The `expert` band this brief left empty is no longer empty.** See `EXPERT-BAND-BRIEF.md`:
> easy 52 / medium 243 / hard 51 / expert 40 = 386.

For a coding agent with a terminal. Read `CLAUDE.md` first.

Small feature with one honest problem inside it. Independent of `NARRATION-BRIEF.md`; either can ship first.

---

## 1. Why

There is no way to warm up on easier questions before a session, or to spend a session only on the
hard ones. Both are ordinary study behaviours and neither is possible today.

The field to do it with already exists on every question and does nothing.

---

## 2. What exists, and the problem with it

`difficulty` is authored on all 346 questions — `easy` 52, `medium` 243, `hard` 51. The loader reads
it, `webapi` returns it, the front end displays it. **Nothing selects on it.**

Two things are wrong with it as it stands.

**It is not validated.** `loader.py` does `str(pick("difficulty", "medium"))`, so `"Medium"`,
`"moderate"` or a typo silently becomes whatever was written, or defaults to medium. A vocabulary
that is never checked drifts, and this one has never been checked.

**It is one author's guess, and 70% of it is the default value.** No one has ever compared these
labels against how the questions actually behave. A `--difficulty hard` filter over 43 questions
labelled hard by the person who wrote them is a weak feature wearing the costume of a real one, and
the tool should not pretend otherwise.

Meanwhile `itemanalysis.py` already computes **empirical** difficulty — the p-value, with a Wilson
interval and a five-attempt gate — and the two notions have never been connected. That connection is
the most interesting part of this work.

---

## 3. What the bank can actually support

Decided: **strict filtering** — picking `hard` serves hard questions only, never topped up from
medium. That is the right call because it keeps the session honest about what it is, and it makes
the thinness of the labels visible instead of hiding it. It also means the interface has to cope
with small and empty result sets, because they are common:

| Domain | easy | medium | hard | total |
|---|---|---|---|---|
| 1 | 9 | 44 | 7 | 60 |
| 2 | 11 | 40 | 9 | 60 |
| 3 | 14 | 41 | 8 | 63 |
| 4 | 10 | 59 | 15 | 84 |
| 5 | 8 | 59 | 12 | 79 |
| **all** | **52** | **243** | **51** | **346** |

**Difficulty composes well with domain and badly with topic.** Across the 180 topic-by-difficulty
combinations, **36 are empty and another 83 hold one or two questions** — so a learner who picks a
topic *and* a difficulty gets nothing about a fifth of the time, and too little to be worth a session
about half the time. Design for that as the normal case, not the edge case.

---

## 4. What to build

**Validate the vocabulary.** `easy` / `medium` / `hard`, and anything else is an **error**, not a
warning. A silently mangled label is data corruption, and the bank is the one thing here that must
stay clean.

**Selection, strict.** `python drill.py drill --difficulty hard`, and a control in the web Drill
screen. It filters the pool *before* the scheduler runs, so spaced repetition still orders whatever
survives. Asking for 20 hard questions in a pool that holds 7 gets you 7 **and a plain statement
that it was 7, and why** — never a silent short session and never a quiet top-up from medium.

**A ramp.** `--difficulty ramp`, and the same option in the tab: start the session on easier
questions and escalate. Two ways to build it, and the choice matters:

- **Reorder only.** Let the scheduler select the session exactly as it does today, then sort those
  questions easy → medium → hard for presentation. The scheduler is untouched, due questions are
  never skipped, and you still get the gentle start. **Prefer this**, and note the honest limitation:
  if the selected set happens to be all medium, there is no ramp that day.
- **Band sampling.** Draw a quota from each difficulty band and let the scheduler order within each.
  A truer ramp that does change what gets served, and with only 51 hard questions bank-wide it will
  exhaust them quickly.

Build the first, use it, and switch only if it turns out to be flat in practice. Say which you built
and why.

**Not in this scope:** comparing authored labels against measured p-values to find labels that are
wrong. That is real and it is deferred — the harness in `SIMULATION-BRIEF.md` now exists to test
such a diagnostic properly, and check 8 there already anticipates it. Do not build it here.

---

## 5. Non-negotiable

1. **Never present an authored label as though it were measured.** Every surface that filters on
   difficulty says which basis it used. "Author-assigned, not yet checked against your results" is
   the honest caption, and it stays until something has actually checked them.
2. **Strict means strict.** No silent top-up from an adjacent band. If the filter yields fewer
   questions than were asked for, the learner is told the number and the reason before they start.
3. **Filtering must not silently defeat the scheduler.** If `--difficulty hard` excludes questions
   that were due today, say so at the end of the session. A learner should not be able to skip their
   due queue without being told they did.
4. **Do not backfill or overwrite authored labels**, and do not infer a label for a question that
   lacks one. An invented label is worse than an unvalidated one, because it looks earned.
5. **`drillkit/`, `drill.py`, `serve.py` stay standard-library only.**

---

## 6. Done

- `easy` / `medium` / `hard` enforced by `validate`, with a test for a rejected value
- `--difficulty` on `drill.py drill`, and a matching control in the web Drill screen
- Strict filtering, applied before the scheduler orders what survives
- Short and empty results handled deliberately in both front ends, with the count and the reason
  shown before the session starts rather than discovered during it
- A ramp mode, built the reorder-only way unless there is a stated reason not to
- Skipped-due-questions disclosed when a filter suppresses them
- Every difficulty surface states that the labels are author-assigned
- `python run_tests.py` green, `python drill.py validate` clean, `npm run build` output committed

---

## 7. How to work

- **The empty case is the feature.** A fifth of topic-plus-difficulty combinations return nothing.
  Whatever you do there is what this will be judged on, more than the happy path.
- **Argue with §4 on the ramp.** It is the least specified part on purpose, and you will learn more
  from building it than I can specify from here.
- If the authored labels turn out to be so unreliable that filtering on them misleads, that is a
  finding worth reporting rather than a feature worth shipping quietly.
- **Ask before**: changing the `difficulty` vocabulary, editing labels in the bank, touching the
  scheduler, or altering anything in `CLAUDE.md` §3.
