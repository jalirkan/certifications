# Certification study system — project brief

Read this before touching anything. It carries decisions that are not recoverable from the code, and
several rules below are ones a capable agent would otherwise break in good faith.

The workstation-level conventions live one level up at `../CLAUDE.md`. This file governs **this
project**, and where the two disagree, this one wins.

---

## 1. What this is and who it is for

An offline study system for **CISA now, CPA after**. Question bank, drill CLI, timed mock exams,
short-form games, and two diagnostic layers.

**Justin** — staff internal auditor, accounting graduate 2026, data science bootcamp background.
Comfortable with Python and the command line; explanations can assume technical literacy. Stated
preference: concise and direct, no padding, no recap of work he watched happen. High tolerance for
being told he is wrong — agreement has cost his projects more than friction ever has.

A **coworker studies alongside him**, which is why profiles exist. The question bank is shared; the
answer history is not.

This is a working tool that gets used before work, not a demo. It has to start instantly and never
lose data.

---

## 2. Current state

| | |
|---|---|
| Question bank | **292 original questions**, all 5 domains, all 50 outline topics covered |
| Per domain | 60 each for D1–D4, 52 for D5 |
| Answer keys | spread A 25% / B 24% / C 26% / D 25% — no positional pattern to exploit |
| Decision rules | 22 documented, 223 of 292 questions mapped, every rule spans ≥2 domains |
| Confusable pairs | 29 documented, 63 questions mapped, **2 known gaps** |
| Study guides | D5 complete; **D1–D4 missing** |
| Tests | **195, all passing** — `python run_tests.py` |
| Front ends | CLI (`drill.py`) and a local web app (`serve.py` serving the built `web/`) |
| Web front end | **Vite + React + TypeScript + Recharts**, source in `frontend/`, builds to `web/` |
| Git | tag `stdlib-only` marks the pre-rebuild, zero-dependency state |

```
certifications/
  drill.py            CLI: drill / exam / game / principles / costumes / stats / items / validate / list
  serve.py            local web app, stdlib http.server, binds 127.0.0.1 only
  run_tests.py        runs every suite
  frontend/           web front end source — Vite + React + TS. `npm run build` emits to web/
  web/                BUILD OUTPUT. Do not hand-edit; it is overwritten by every build
  drillkit/
    loader.py           question bank loading, validation, profiles, pairs, principles
    scheduler.py        spaced-repetition-lite selection
    session.py          interactive drill loop
    stats.py            accuracy roll-ups
    store.py            append-only attempt log
    exam.py             blueprint sampling, exam state, scoring
    examsession.py      timed exam runner and report
    games.py            Cold Read and Autopsy, question-type classifier
    itemanalysis.py     difficulty, discrimination, distractor quality
    principles.py       decision-rule diagnosis and study card
    webapi.py           JSON API over all of the above
  tests/              6 suites
  cisa/
    outline.json            ISACA exam content outline — the source of truth for topic tags
    principles.json         22 decision rules + the questions each decides
    confusable-pairs.json   29 confusions + discriminator + the trap + mapped questions
    questions/              292 questions, one file per domain-section
    cases/                  branching audit cases + SCHEMA.md (3 written, ~35 needed)
    study-guides/           topic checklists with notes and a status column
    results/                answer logs — PERSONAL DATA, see rule 13
  cpa/                reserved sibling, activated after CISA
```

---

## 3. Hard rules

These are decisions, not preferences. Breaking them silently makes the tool dishonest or destroys
data, which is worse than leaving it alone.

**Content integrity**

1. **Never reproduce ISACA, QAE, or any other copyrighted exam questions.** Every question in the
   bank is original and must stay that way. This is not negotiable and applies to every future batch.
2. **Verify exam facts online before writing them** — domain weights, topic lists, exam length,
   passing score. These change. The outline was last verified **2026-07-26** against isaca.org.
   Update that date when you re-verify.
3. **Question `topic` values must match `cisa/outline.json` exactly.** `python drill.py validate`
   enforces this. Run it after any edit to the bank.
4. **Question banks are data, never hardcoded into the engine.**
5. **The engine stays certification-agnostic** so `cpa/` works without code changes.

**Honesty about statistics** — the reason the tool is trustworthy

6. **Every statistic carries its uncertainty.** Accuracy is reported with Wilson intervals and gated
   on minimum sample sizes, never as a bare percentage. 2 out of 2 is not 100%; it is 34–100%.
   A small sample must visibly read as *unknown*.
7. **Never present the estimated scaled exam score as a prediction.** ISACA's scaling is undisclosed
   and the raw threshold moves between forms. Every surface showing it carries the caveat. Do not
   relabel it "predicted", "projected" or "readiness".
8. **Short-form games stay out of the real evidence.** Cold Read and Autopsy write to
   `games.jsonl`, never `attempts.jsonl`, so they cannot reach headline accuracy, item analysis or
   the scheduler. A five-second answer is not the same evidence as a worked scenario. There is a
   test enforcing this — do not weaken it.
9. **Costumes is not a game.** Full questions answered normally, so it logs to `attempts.jsonl` as
   real evidence.
10. **Every decision rule must appear in at least two domains.** A rule confined to one domain
    cannot demonstrate transfer, which is the only reason the axis exists. Enforced by test.
11. **Never force a question onto a principle to raise coverage.** Definitional questions
    legitimately have no governing rule. `validate` reports judgment-worded questions with no rule
    as a *bank-quality signal* — those stems usually promise judgment while testing recall.
12. **Answer keys never reach the browser before the user commits.** Questions go out as stem and
    options; the key and rationale come back in the answer response. Enforced by test.

**Data**

13. **`cisa/results/` is Justin's real study history.** Never clear it to tidy up after testing —
    use a throwaway `--profile` or `X-Profile` value instead. Never commit it; it is gitignored.
14. **Results are per profile; the bank is shared.** `cisa/results/profiles/<name>/`. Mixing two
    learners into one history corrupts the scheduler and every diagnostic.

**Dependencies**

15. **`drillkit/`, `drill.py` and `serve.py` stay standard-library only.** Not dogma — that code is
    finished, tested and dependency-free, so adding dependencies buys new risk and no new
    capability. The principle is *put dependencies where rewrites are cheap.*
16. **The front end may use a real build.** That constraint was dropped deliberately. See §5.

---

## 4. Design decisions worth not relitigating

- **Two diagnostic axes.** Topics answer "what should I study"; decision rules answer "which
  reasoning habit is costing me marks across every domain". The second transfers to questions that
  do not exist yet, which is the actual exam condition. Simulation showed a weakness spread across
  topics is roughly **4× more visible on the rule axis** — there is a test measuring this.
- **Rules carry a misapplication and a scope note.** The misapplication is what the diagnostic
  reports back ("you reach for detective controls when the stem asks what prevents"). The scope note
  says when the rule does *not* apply, because treating a scoped rule as universal is its own trap.
- **Mappings live in one file, not as tags across 292 question files.** Both `principles.json` and
  `confusable-pairs.json` hold their own question lists. One place to review, cheap to extend.
- **Topics rank by the lower confidence bound, not the point estimate.** Deliberately conservative:
  it surfaces under-tested topics alongside genuinely weak ones, and drilling either resolves the
  uncertainty.
- **Exam sampling follows the published blueprint** (18/18/12/26/26 → 27/27/18/39/39 of 150) using
  largest-remainder so counts sum exactly. Weights come from the outline, not from what happens to
  be in the bank, so an empty domain reports a shortfall instead of vanishing.
- **The exam clock only runs while a sitting is open**, and can only move forward. A reloaded tab
  cannot rewind it.
- **No gamification, ever.** No streaks, XP, badges, confetti, leaderboards. They measure engagement,
  not learning, and were explicitly rejected.

---

## 5. What is next

1. ~~**Front end rebuild**~~ — **done 2026-07-31.** Vite + React + TypeScript + Recharts in
   `frontend/`, building to `web/`. `FRONTEND-BRIEF.md` remains as the spec it was built against.
   Working on it: `cd frontend && npm run build`, then `python serve.py` as before. `npm run dev`
   proxies `/api` to port 8765 for a hot-reload loop against the real engine.
2. **Study guides for Domains 1–4** at the depth of the D5 one. Highest-value content work and it
   needs no build tooling.
3. **Close the two confusable-pair gaps** — nothing in the bank tests **verification vs validation**
   or **FAR / FRR / CER**. `validate` warns about both.
4. **Look at the 16 judgment-worded questions that map to no decision rule.** `validate` lists them.
   They are usually stems that promise judgment and test recall, making them the weakest CISA-style
   items in the bank and the first candidates for rewriting.
5. **Deepen the bank** where `items` flags thin coverage or badly-behaved questions.
6. **Stand up `cpa/`** after CISA. Verify the current AICPA blueprints first — the exam changed
   under CPA Evolution, and CPA includes task-based simulations that this multiple-choice engine
   does not model.

---

## 6. How to work on this

- **Test before handing anything over, and include the tests.** `python run_tests.py` must stay
  green. This has held for the whole project and is the reason it can be trusted.
- **Run `python drill.py validate` after any edit to the bank, pairs or principles.** It fails on
  duplicate IDs, bad answer keys, missing distractor explanations, unknown topics and broken
  references; it warns on bank-quality signals.
- **Trust no report — verify on disk.** A full mock-exam integration run once printed a clean,
  plausible report while silently expiring 143 of 150 questions. It surfaced only by disbelieving
  the summary and reading the numbers.
- **Argue with this file.** If evidence from running the code contradicts something here, the
  evidence wins — say so and update the file rather than working around it.

**Which tool for which work.** Content, study guides, question batches, analysis and documentation
are Cowork-shaped. Anything with an install/build/run loop — the front end rebuild especially —
belongs in Claude Code, which can `npm install` and iterate.

**House style for questions.** Judgment stems (BEST / MOST / FIRST / GREATEST / PRIMARY / LEAST),
four options, one defensible answer and three plausible distractors, written from the auditor's
seat. Explain every wrong answer — the distractor explanations carry more learning value than the
stem. Vary the answer key.

**Ask before**: changing the question schema, altering the honesty rules in §3, clearing any results
file, or adding a dependency to `drillkit/`.

Last updated: 2026-07-31
