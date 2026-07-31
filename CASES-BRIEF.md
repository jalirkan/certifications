# Branching cases — handoff brief

> **Status: engine, API and both interfaces built 2026-07-31.** All three cases play end to end in
> the browser and the terminal. Suite went 233 → 259.
>
> - `drillkit/casesession.py` — session state, choosing, the debrief. `drillkit/caserunner.py` —
>   terminal runner. `drillkit/cases.py` was not modified.
> - API as sketched in §5, with one addition: the debrief carries an `endings_index` so the client
>   can label where an option you did *not* take would have led. "Would have ended: capability
>   remains untested (weak)" teaches more than "that option was poor".
> - CLI built: `python drill.py case [id] [--list] [--resume ID] [--stats]`.
> - §4.1 is enforced by an allow-list (`public_option`) rather than a filter, so a field added to
>   the schema later cannot leak by default. Tested against all three cases.
>
> Two things worth knowing, neither of them blocking — see the closing notes in §8.

For a coding agent with a terminal. Read `CLAUDE.md` first, then this, then
`cisa/cases/SCHEMA.md`.

Less prescriptive than `FRONTEND-BRIEF.md` on purpose. The data layer is settled and tested; the
session engine, API and interface are not, and you will learn things from building them that are not
knowable from here. Where this brief does not tell you how, that is deliberate.

---

## 1. What this feature is

A branching audit case drops the learner into an engagement. They make five to eight decisions, the
situation moves in response, and they find out how it went **at the end** — not at each step.

It exists because a multiple-choice question cannot express two things the exam actually tests:
sequential judgment, where your first decision changes what you face next; and graded correctness,
where an option is defensible-but-worse rather than simply wrong.

This is also the feature most likely to make someone stop and look at the repository, which matters
because the project doubles as a portfolio piece for audit and GRC roles.

---

## 2. What already exists — do not rebuild it

| | |
|---|---|
| Format | `cisa/cases/SCHEMA.md` — read this before anything else |
| Content | 3 complete cases: D1 audit execution, D4 business resilience, D5 incident response |
| Loader + validation | `drillkit/cases.py` — stdlib, tested, wired into `python drill.py validate` |
| Tests | `tests/test_cases.py` — 38 tests. Total suite is **233 and must stay green** |
| Path analysis | `cases.score_path()`, `reachable()`, `longest_path()` already implemented |

The three cases are real study material regardless of whether this feature ships. Treat them as
content, not fixtures.

**Three concepts you need from the schema, because they drive the whole design:**

- **Graded quality** — `best` / `defensible` / `poor`, not right/wrong.
- **Deferred feedback** — each option has a neutral `consequence` shown as the learner moves, and a
  `why` withheld for the debrief.
- **Taints** — some options fix the outcome no matter what follows. Losing your independence is not
  recovered by answering the next question well. `resolve_ending()` already handles precedence.

---

## 3. What to build

**Session engine.** Resumable, like exams are. State is the case id, the path taken so far, the
current node, and any taints collected. Persist it; a case is 10–15 minutes and a closed tab should
not lose it.

**API.** Roughly:

```
GET  /api/cases                    list: id, title, domain, topics, principles, minutes, attempted?
POST /api/case/start   { case_id } → session, opening, first node
POST /api/case/choose  { session, node, key } → consequence, next node OR the ending marker
GET  /api/case/{session}/debrief   → the full teaching payload
GET  /api/case/{session}           → resume
```

Shape it however the front end actually needs. The one thing that is not negotiable is §4.

**Runner UI.** Opening, then one decision at a time. On choosing: show the `consequence`, move on.
No verdict, no colour, no score counter. Resist every instinct to reassure the learner mid-case —
sitting with an uncertain choice is the thing being trained.

**Debrief.** This is where the value is, and it deserves more design effort than the runner.

At minimum: the path walked, and at each node what they chose, what the best option was, and the
`why` for both. Then the ending with its narrative and verdict.

Better: **show the branches not taken.** The case is a small graph and the learner has only seen one
thread through it. Seeing the tree — and where their thread diverged — is most of the teaching.

If a taint fired, say so explicitly and point at the decision that fixed the outcome. `score_path()`
returns `overridden` for exactly this. "Your final answers were sound, but the outcome was
determined four decisions earlier when you agreed to omit the finding" is the single most valuable
sentence the feature can produce.

---

## 4. Non-negotiable

1. **`quality` and `why` must never reach the client before the debrief.** Same rule as answer keys
   in `CLAUDE.md` §3.12, same reason. If the browser can see which option is `best`, the feature is
   pointless. Send `key`, `text` and nothing else.
2. **No verdict during the run.** The `consequence` is neutral narration by design — there are tests
   asserting authors keep it that way. Do not add scoring, progress indicators, or reassurance
   between decisions.
3. **Cases log to their own file**, `cases.jsonl`, alongside `attempts.jsonl` and `games.jsonl`.
   A case is not a four-option MCQ; letting it reach item analysis or the spaced-repetition
   scheduler would corrupt both. Follow the pattern in `drillkit/games.py`.
4. **Do not wire cases into the principle diagnostic yet.** That is deliberately a later phase —
   prove the format works against real use before letting it touch a working diagnostic. Report
   case results on their own surface for now.
5. **Never a percentage.** `score_path()` returns a profile — counts of best/defensible/poor, the
   ending, the verdict — because collapsing a path to one number throws away the part that teaches.
   Do not add a score in the UI.
6. **`drillkit/`, `drill.py` and `serve.py` stay standard-library only.** The front end may use
   whatever `frontend/` already depends on.

---

## 5. How to work

- **Argue with this brief.** You will be running the thing; I could not. If the API shape here is
  awkward once you build against it, change it and say why.
- **Build the CLI runner too, or say why not.** Every other feature works from both `drill.py` and
  the web app. A case runner that only exists in the browser breaks that symmetry, and the CLI is
  where the format gets stress-tested fastest.
- **Play all three cases end to end before calling it done**, including at least one tainted path
  and one path that reaches a `strong` ending. If the debrief does not teach you something about
  audit judgment, it is not finished.
- **Ask before**: changing `cisa/cases/*.json`, the schema, `drillkit/cases.py`, or anything in
  `CLAUDE.md` §3.

---

## 6. Done

- All three cases playable end to end, in the browser and ideally the CLI
- Sessions resume after a browser restart
- `quality` and `why` verifiably absent from any pre-debrief payload — add a test, as the existing
  answer-key rule has
- Cases write only to `cases.jsonl`; `attempts.jsonl` byte-identical before and after a run
- Debrief shows the path, the alternatives at each node, and names the deciding decision when a
  taint fired
- `python run_tests.py` green, `python drill.py validate` clean
- `npm run build` output served by `python serve.py` with no Python change

---

## 7. After this

Roughly 35 more cases are needed for the feature to carry real weight, and those are authored in
Cowork rather than here — writing them is content work, not engineering. Two other things queued
behind this: confidence capture with calibration curves, and an FSRS scheduler fitted to the
learner's own review history. Neither blocks this work.

---

## 8. Notes from building it

Two content observations. Both are for you to decide on — I did not change `cisa/cases/*.json`.

**1. `d4-the-successful-test`'s taint can never fire.** `accepted-scope-defence` is declared as
pointing at `end-unproven`, and the only option carrying it (`the-scope-defence` A) already has
`"next": "end-unproven"`. So `resolve_ending()` returns the ending the graph had already reached,
`overridden` is always false, and the "your outcome was fixed earlier" sentence — the most valuable
thing the debrief produces — never appears for this case. The validator does not warn, because an
option *does* apply the taint; it just cannot change anything.

The other two cases route their tainted options back into the graph (`d5` to `the-omission-request`
and `backup-evidence`, `d1` to `the-recommendation`), so the override fires properly there. If you
want d4 to teach the same lesson, point option A at a node that continues rather than at the ending.

**2. `d4` reaches `end-strong` with zero best choices.** Playing D/B/B/B/C gives 0 best, 4
defensible, 1 poor — and a strong ending. That is the graph converging, which §"Make recovery
possible" in the schema asks for, and the profile does carry the nuance the ending hides. Worth
knowing that for this case the ending alone does not discriminate much; the counts do all the work.
It is also the clearest argument for rule §4.5 — a single percentage here would have been actively
misleading in both directions.

**One CLI bug found and fixed while playing:** `case --stats` crashed on the row for an overridden
run, because the marker used `←`, which Windows cannot encode when stdout is redirected to a file
or a pipe (cp1252). Now ASCII, with a test asserting both new modules stay cp1252-safe.
