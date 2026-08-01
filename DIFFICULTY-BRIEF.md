# Difficulty selection — handoff brief

For a coding agent with a terminal. Read `CLAUDE.md` first.

Small feature with one honest problem inside it. Independent of `NARRATION-BRIEF.md`; either can ship first.

---

## 1. Why

There is no way to warm up on easier questions before a session, or to spend a session only on the
hard ones. Both are ordinary study behaviours and neither is possible today.

The field to do it with already exists on every question and does nothing.

---

## 2. What exists, and the problem with it

`difficulty` is authored on all 346 questions — `easy` 52, `medium` 227, `hard` 43. The loader reads
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

## 3. What to build

**Validate the vocabulary.** `easy` / `medium` / `hard`, and anything else is an **error**, not a
warning. A silently mangled label is data corruption, and the bank is the one thing here that must
stay clean.

**Selection.** `python drill.py drill --difficulty hard`, plus the web equivalent. It filters the
pool *before* the scheduler runs, so spaced repetition still orders whatever survives the filter.

**A ramp.** Something like `--difficulty ramp` that moves easy → medium → hard across a session.
This is the mode most likely to get used daily, so it deserves more thought than the plain filter.

**The part that matters: check the labels against reality.** In `items`, for every question with
enough attempts, compare the authored label against the empirical p-value and report where they
disagree — a question labelled `easy` that is missed most of the time, or a `hard` one nobody ever
gets wrong. That is a bank-quality signal of the same kind as the orphan-principle flag, and it is
the only route by which these labels ever become trustworthy.

Do not auto-correct the labels from it. Report the disagreement and let a human decide.

---

## 4. Non-negotiable

1. **Never present an authored label as though it were measured.** Every surface that filters or
   reports on difficulty says which basis it used. "Authored difficulty (not yet validated against
   your results)" is the honest caption until the data exists.
2. **Empirical difficulty keeps its interval and its minimum-attempts gate.** `CLAUDE.md` §3.6.
   Two attempts is not a p-value.
3. **Filtering must not silently defeat the scheduler.** If `--difficulty hard` excludes questions
   that were due today, say so at the end of the session. A learner should not be able to skip their
   due queue without being told.
4. **Do not backfill or overwrite authored labels automatically**, and do not infer a label for a
   question with thin data. An invented label is worse than an unvalidated one, because it looks
   earned.
5. **`drillkit/`, `drill.py`, `serve.py` stay standard-library only.**

---

## 5. Done

- `easy` / `medium` / `hard` enforced by `validate`, with a test for a rejected value
- `--difficulty` on drill in both front ends, filtering before scheduling
- A ramp mode that someone would actually use twice
- `items` reports authored-versus-empirical disagreement, gated on attempts, with intervals
- Every difficulty surface states its basis
- Skipped-due-questions disclosed when a filter suppresses them
- `python run_tests.py` green, `python drill.py validate` clean

---

## 6. How to work

- **Argue with this brief.** The ramp is the least specified part on purpose; you will learn more
  from building it than I can specify from here.
- If the authored labels turn out to be so unreliable that filtering on them is misleading, that is
  a finding worth reporting rather than a feature worth shipping quietly.
- **Ask before**: changing the `difficulty` vocabulary itself, editing labels in the bank, or
  altering anything in `CLAUDE.md` §3.
