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
| Question bank | **386 original questions**, all 5 domains, all 60 outline topics covered |
| Per domain | 67 for D1/D2, 68 for D3, 95 for D4, 89 for D5 |
| Answer keys | spread A 25% / B 24% / C 26% / D 24% — no positional pattern to exploit |
| Difficulty bands | easy 52 / medium 243 / hard 51 / expert 40; selectable and strict |
| Detection report card | `DETECTION.md` — the diagnostics scored against planted weaknesses |
| Decision rules | 23 documented, 308 of 386 questions mapped, every rule spans ≥2 domains |
| Confusable pairs | 29 documented, 69 questions mapped, **no gaps** |
| Study guides | **all five domains**, same depth |
| Branching cases | 19 written (~35 needed), blueprint-weighted; 52 of 60 topics, all 23 rules |
| Tests | **483, all passing** — `python run_tests.py` |
| Front ends | CLI (`drill.py`) and a local web app (`serve.py` serving the built `web/`); certs switchable in the browser via `X-Cert`, dark/light themes |
| Sibling cert | `cpa-aud/` stood up 2026-08-27: verified Jan-2026 AUD blueprint outline, 60-question reviewed seed bank, own format (78 MCQ / 120 min / 0–99, pass 75) |
| Web front end | **Vite + React + TypeScript + Recharts**, source in `frontend/`, builds to `web/` |
| Git | tag `stdlib-only` marks the pre-rebuild, zero-dependency state |

```
certifications/
  drill.py            CLI: drill / exam / case / game / calibration / simulate / principles / costumes / stats / items / validate / list
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
    cases.py            branching-case data, validation, path analysis
    casesession.py      case session state, choosing, the debrief
    caserunner.py       terminal runner for cases
    itemanalysis.py     difficulty, discrimination, distractor quality
    principles.py       decision-rule diagnosis and study card
    calibration.py      confidence vs accuracy, the dangerous quadrant, coverage projection
    simulation.py       synthetic learners and the detection report card
    webapi.py           JSON API over all of the above
  tests/              9 suites
  cisa/
    outline.json            ISACA exam content outline — the source of truth for topic tags
    principles.json         23 decision rules + the questions each decides
    confusable-pairs.json   29 confusions + discriminator + the trap + mapped questions
    questions/              386 questions, one file per domain-section
    cases/                  branching audit cases + SCHEMA.md (19 written, ~35 needed)
    study-guides/           topic checklists with notes and a status column
    results/                answer logs + per-profile settings.json — PERSONAL DATA, see rule 13
  cpa-aud/            CPA AUD Core: verified outline + original seed bank
  cpa/                pointer README - CPA is four exams, one cert folder each
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
  do not exist yet, which is the actual exam condition.
  **The original justification for this was wrong and `DETECTION.md` disproved it.** The claim was
  that a rule-level weakness is roughly 4× more visible on the rule axis — near-invisible by topic.
  Against the real bank the topic axis finds it essentially 100% of the time, because rules are not
  spread evenly over topics and most rules dominate one. What survives: studying the three weakest
  topics reaches only **14–41%** of the questions a planted rule governs, so the topic report names
  one affected subject while the rule report names the cause still costing marks elsewhere. Keep the
  axis; state the narrower claim. Do not restore the old one.
- **Rules carry a misapplication and a scope note.** The misapplication is what the diagnostic
  reports back ("you reach for detective controls when the stem asks what prevents"). The scope note
  says when the rule does *not* apply, because treating a scoped rule as universal is its own trap.
- **Mappings live in one file, not as tags across 21 question files.** Both `principles.json` and
  `confusable-pairs.json` hold their own question lists. One place to review, cheap to extend.
- **Topics rank by the lower confidence bound, not the point estimate.** Deliberately conservative:
  it surfaces under-tested topics alongside genuinely weak ones, and drilling either resolves the
  uncertainty.
- **Exam sampling follows the published blueprint** (18/18/12/26/26 → 27/27/18/39/39 of 150) using
  largest-remainder so counts sum exactly. Weights come from the outline, not from what happens to
  be in the bank, so an empty domain reports a shortfall instead of vanishing.
- **The exam clock only runs while a sitting is open**, and can only move forward. A reloaded tab
  cannot rewind it.
- **Item discrimination is not measurable here, and that is settled.** `DETECTION.md` check 4 asks
  whether a question that measures nothing gets flagged. It does not: 10% detection. Spotting it
  needs per-item discrimination, discrimination needs roughly 20 attempts *on the same question*,
  and one learner's answers spread over 386 questions give about seven — one item in 334 was
  measurable on a sample run. The three options were to drop the claim, pool answers across
  profiles so items accumulate attempts faster, or document the limit. **Documented.** Pooling was
  rejected because it cuts against rule 14, and mixing two learners to rescue one statistic would
  corrupt the scheduler and every other diagnostic to fix the weakest one.
  Do not "fix" this by loosening the thresholds. That was the original bug: the flags fired on 79%
  of all items, which inflated their apparent detection because flagging four items in five catches
  most planted ones by luck. The Bank screen says the stat is not measurable rather than showing a
  bare dash.

- **Confidence feeds the scheduler, and `guess` is the only level that changes anything.** A correct
  answer rated a guess holds its spacing interval instead of extending it — a lucky answer should
  not buy a 35-day silence on material the learner cannot do. It *holds* rather than resets, because
  a guess that was right is still not a miss. `unsure` advances normally, since it sits above chance
  in every curve seen so far and the failure being prevented is specifically the guessed-correct
  one. **An unrated answer is never read as a guess**: everything logged before capture existed
  carries `confidence == ""`, `store.py` refuses to backfill it, and treating a blank as a guess
  would silently rewind the schedule of a learner's entire earlier history.
  **And the rule only switches on once that learner's confidence has earned it.** Taking a
  self-rating at face value is only sound if the rating means something, and `calibration.py`
  names the case where it does not: a flat curve, where confidence carries no information about
  correctness. `scheduler.confidence_is_informative()` gates on the same evidence bar used
  everywhere else — a positive confident-vs-rest gap, enough answers behind it, and an interval
  excluding zero. Below that bar, scheduling is exactly what it was before.
  That gate was **found, not designed**: applying the rule unconditionally dropped check 7 from
  trustworthy-at-1000 to never (88% detection to 23%), because check 7's learner has deliberately
  flat confidence and a third of their correct answers are rated "guess" at random. Holding a
  question on a coin flip churns the schedule and buys nothing.
  Deferred until check 7 measured the signal in the first place. Changing the scheduler changes
  every simulated history, so re-run `python drill.py simulate --write` after touching it.

- **No gamification, ever.** No streaks, XP, badges, confetti, leaderboards. They measure engagement,
  not learning, and were explicitly rejected.

---

## 5. What is next

1. ~~**Front end rebuild**~~ — **done 2026-07-31.** Vite + React + TypeScript + Recharts in
   `frontend/`, building to `web/`. `FRONTEND-BRIEF.md` remains as the spec it was built against.
   Working on it: `cd frontend && npm run build`, then `python serve.py` as before. `npm run dev`
   proxies `/api` to port 8765 for a hot-reload loop against the real engine.
2. ~~**Study guides for Domains 1–4**~~ — **done 2026-07-30.** All five domains now have a guide at
   the same depth: tracker table, domain reflexes, every outline topic, and a closing table of that
   domain's confusable pairs. ~1,800 lines total in `cisa/study-guides/`.
3. ~~**Close the two confusable-pair gaps**~~ — **done.** Six new questions cover verification vs
   validation and FAR / FRR / CER. `validate` is clean, no warnings.
4. ~~**Look at the 16 judgment-worded questions that map to no decision rule**~~ — **done.** Three
   were testing a rule the taxonomy lacked, now principle 23 `protection-follows-data`. The other 13
   are genuinely recall and carry an explicit `no_principle: true` flag.
5. **Deepen the bank, and do it where the blueprint bites.** Not "more questions" generally — a
   150-question mock draws 39 from Domain 5's 55-question pool, so the second mock exam is already
   re-serving remembered questions. D4 and D5 need roughly +60 and +65 to reach the headroom D3
   already has. `items` flags badly-behaved questions on top of that.
6. **Build the synthetic learner harness** — `SIMULATION-BRIEF.md`. Plant a known weakness in a
   generated study history and score whether the diagnostics find it, with a negative control and a
   sample-size sweep. This is what lets the project make claims about itself.
6. **Stand up `cpa/`** — **started 2026-08-27, as `cpa-aud/`.** CPA is four separate exams, so
   each section is its own cert — one cert = one exam is what blueprint sampling, mock timing and
   the scaled-score caveat all assume; `cpa/` keeps a pointer README. Done: AUD outline verified
   against the January-2026 blueprint (78 MCQ + 7 TBS, 50/50 scoring, 0–99 pass 75 — the tool
   models the MCQ half and says so on every exam surface), a 60-question original seed bank with
   every item adversarially reviewed, validate clean with no warnings. CISA remains the priority.
   Deliberately not done: AUD decision rules and confusable pairs (rules earn their place by
   recurring across areas — seed them once real drilling shows what recurs, per rule 11), study
   guides, bank depth (a 78-question mock over a 60-question bank reports its shortfall honestly),
   and FAR / REG / a discipline, which follow the same pattern when their time comes.

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

Last updated: 2026-08-27
