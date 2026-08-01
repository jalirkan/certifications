# Certification study system

Offline study tooling for **CISA** now, **CPA** later. Nothing to install to *use* it, and **no
network access at runtime** — no API key, no account, no model. It runs on a plane.

## Two ways to use it

```bash
python serve.py      # web app — opens in your browser
python drill.py      # command line — same engine, same data
```

Both front ends read and write the same files, so you can drill in the browser and check `stats` in
the terminal.

**The engine, the CLI and the server are Python standard library only** — `drillkit/`, `drill.py`
and `serve.py` have no required third-party dependency, so the tool works on any Python 3.7+ with
nothing installed. (There is exactly one optional import, PyYAML, reached only if you deliberately
store a question batch as `.yaml`; everything ships as JSON.) The server binds to `127.0.0.1` only.

**The browser front end is a built React app** (Vite, TypeScript, Recharts) living in `frontend/`.
Its compiled output is committed to `web/`, so `python serve.py` works without Node — you only need
Node if you want to *change* the interface:

```bash
cd frontend && npm install && npm run build     # rebuild web/ after editing frontend/src
npm run dev                                     # hot reload, proxies /api to port 8765
```

That split is deliberate. Engines, data models and CLIs are long-lived and stay lean; interfaces get
rewritten anyway, so they use real tools. It was a stdlib-only vanilla-JS front end until
2026-07-31, and the earlier version is tagged `stdlib-only` if you ever want it back.

### Study profiles

Two people can share one question bank without polluting each other's history:

```bash
python drill.py --profile justin drill -n 20
python serve.py       # then pick a profile in the sidebar
```

Results live in `cisa/results/profiles/<name>/`. Without a profile you get the shared default.
This matters more than it sounds — the spaced-repetition scheduler and every diagnostic are
modelling one learner, and mixing two people produces a picture of neither.

```
certifications/
  drill.py                  the CLI you actually run
  serve.py                  local web server, 127.0.0.1 only
  run_tests.py              runs every test suite
  drillkit/                 the engine (certification-agnostic, stdlib only)
    loader.py                 question bank loading, validation, profile settings
    scheduler.py              spaced-repetition-lite selection
    session.py                interactive drill loop
    stats.py                  accuracy roll-ups
    store.py                  append-only attempt log
    exam.py                   mock exam sampling, state and scoring
    examsession.py            timed exam runner and report
    itemanalysis.py           difficulty, discrimination, distractor quality
    principles.py             the decision-rule diagnostic
    calibration.py            confidence vs accuracy
    games.py                  short-form games, logged separately
    cases.py                  branching case format, loading and graph validation
    casesession.py            case state, choices, debrief
    caserunner.py             terminal runner for cases
    webapi.py                 JSON API over the same engine
  frontend/                 React + TypeScript source for the browser app
  web/                      its built output, committed so serve.py needs no Node
  tests/                    364 unit tests
  cisa/
    outline.json            ISACA exam content outline, all 5 domains (structural reference)
    study-guides/           one guide per domain, with a status column you mark up
    questions/              question banks as JSON data, one file per domain-section
    cases/                  branching audit cases, plus SCHEMA.md
    principles.json         the decision-rule taxonomy
    confusable-pairs.json   documented confusions and the questions that turn on each
    results/
      attempts.jsonl          your answer log, append-only
      games.jsonl             short-form results, deliberately a separate file
      profiles/<name>/        per-learner histories over the shared bank
  cpa/                      reserved sibling, same shape, for after CISA
```

The engine knows nothing about CISA specifically. Anything with an `outline.json`, a `questions/`
folder and a `results/` folder works — which is how CPA slots in later without a rewrite.

---

## Requirements

Python 3.7 or newer. Check with `python --version`. Nothing else to study.

If `python` is not recognized on Windows, try `py` instead, or install Python from python.org and
tick "Add python.exe to PATH".

Node is needed **only to rebuild the browser interface** after editing `frontend/src`. The compiled
app is committed, so studying never requires it.

---

## Daily drilling

From the `certifications` folder:

```bash
python drill.py drill --domain 5 -n 20        # 20 Domain 5 questions
python drill.py drill --topic encryption -n 10 # substring match on topic name
python drill.py drill --section B -n 15        # just one section
python drill.py drill --mode weakest -n 15     # worst lifetime accuracy first
python drill.py drill --mode due -n 20         # only what the spacing schedule says is due
python drill.py drill -n 10 --why              # show why each question was selected
```

Answer with `A`, `B`, `C` or `D`. Type `q` to stop early — everything answered so far is saved.
After each answer you get the reasoning for the correct option **and** for each distractor, which is
where most of the learning happens. Read the wrong-answer explanations even when you got it right.

### How questions get chosen

`--mode smart` (the default) orders the pool in three tiers:

1. **Anything you missed last time**, worst lifetime accuracy first.
2. **Anything you have never seen.**
3. **Everything else**, most overdue first.

Tier 3 uses a Leitner-style ladder. Each consecutive correct answer moves a question to a longer
interval — 1, 3, 7, 16, then 35 days. One wrong answer resets it to zero and drops it back to tier 1.
Lifetime accuracy is a tiebreaker throughout, so a question you have missed repeatedly keeps
resurfacing even after one lucky correct answer.

Use `--mode due` once you have been through the bank a few times: it holds back anything still
inside its interval, so you only see what the schedule says you are about to forget.

---

## Timed mock exams

```bash
python drill.py exam                       # full 150 questions / 240 minutes
python drill.py exam -n 50 --minutes 80    # shorter timed set
python drill.py exam --domain 4            # timed practice on one domain
python drill.py exam --list                # saved exams and their status
python drill.py exam --resume <id>         # continue where you left off
python drill.py exam --review <id>         # re-score and walk the missed questions
```

Deliberately unlike a drill. Questions are sampled to the **published blueprint weights**
(18 / 18 / 12 / 26 / 26, which works out to 27 / 27 / 18 / 39 / 39 questions), spread across topics
within each domain, and **you get no feedback until you submit**. The point is rehearsing pacing and
endurance, not learning individual items.

Inside the exam:

| Command | Effect |
|---|---|
| `A` `B` `C` `D` | answer and advance |
| `n` / `p` | next / previous |
| `g 42` | jump to question 42 |
| `f` | flag or unflag for review |
| `r` | list flagged and unanswered questions |
| `s` | progress summary with pacing budget |
| `e` | end and score |
| `x` | save and exit — the clock stops, resume later |
| `?` | command help |

The clock only runs while a sitting is open, so `x` genuinely pauses it. State is saved atomically
after every action, so closing the terminal loses nothing. If time runs out the exam auto-submits.

Answered questions are written into the normal attempt log tagged `mode=exam`, so exam performance
feeds `stats`, `items` and the drill scheduler — anything you miss under exam pressure comes back
first in your next drill.

### Reading the exam report

You get raw score, per-domain accuracy against blueprint weight, pacing, the slowest questions, and
questions you flagged but answered correctly (unsure, got lucky — worth revisiting even though the
score looks fine).

The **"where the lost marks actually are"** section multiplies each domain's accuracy gap by its exam
weight. A 60% in Domain 4 costs you more than a 50% in Domain 3, and that ranking is where study time
should go.

**On the estimated scaled score:** ISACA converts raw scores using an undisclosed psychometric
process, and the raw threshold moves between exam forms. The estimate here is a transparent
approximation anchored on the two published facts — 450 passes, the scale runs 200–800 — plus the
widely reported observation that passing candidates tend to be around 70% raw. Treat anything within
about 50 points of 450 as too close to call. It is a rough gauge, not a prediction.

---

## The web app

```bash
python serve.py                 # http://127.0.0.1:8765
python serve.py --port 9000     # if that port is busy
python serve.py --no-browser    # do not open a window
```

Eight screens, all reading the same data as the CLI:

- **Dashboard** — accuracy by domain with **confidence intervals drawn as whiskers**, so a wide bar
  visibly says "not enough evidence" instead of implying a precise percentage. Weakest rules and
  topics, with one-click drills into either.
- **Drill** — keyboard-first: `A`–`D` or `1`–`4` to answer, `Enter` to advance. When you answer,
  **each explanation attaches to the option it explains** rather than arriving as a list you have to
  map back yourself. The governing decision rule appears underneath.
- **Mock exam** — timer, flag-for-review, and a **question palette** showing answered / flagged /
  current at a glance so you can navigate a 150-question paper the way you would the real one.
  Resumable across browser restarts; the clock stops when you save.
- **Cases** — branching audit scenarios, one decision at a time, with the debrief withheld to the end.
- **Short form** — Cold Read and Autopsy, with the options genuinely withheld until you commit.
- **Decision rules** — the diagnostic, plus the generated study card.
- **Calibration** — whether you knew that you knew. The curve, the confident-and-wrong list, and
  the gap with an interval on it.
- **Question bank** — item analysis and the confusable-pair reference.

**Answer keys never reach the browser before you commit.** A question arrives as stem and options
only; the key and the rationale come back in the response to your answer. Opening devtools during a
timed exam gets you nothing, and there is a test asserting it.

---

## Decision rules — the diagnostic that names the habit

```bash
python drill.py principles                 # which reasoning habits cost you marks
python drill.py principles --list          # the 23 rules and their coverage
python drill.py principles --card          # study card, generated from the taxonomy
python drill.py costumes                   # one rule, one question per domain
python drill.py costumes --principle prevent-first
python drill.py drill --mode principle -n 15   # target your weakest rules
```

CISA has an implicit value hierarchy that generates answers across every domain — risk assessment
before control selection, prevent beats detect, accountability cannot be outsourced, design evidence
is not operating evidence, contain before recover. Twenty-three of these rules are documented in
`cisa/principles.json`, each mapped to the bank questions it decides.

**Why this is a different question from `stats`.** A topic report says *study encryption*. A rule
report says *you reach for detective controls when the stem asks what prevents* — one habit, costing
marks in all five domains, fixable in an afternoon. It is also the only axis here that transfers to
questions that do not exist yet, which is the actual exam condition.

**This claim used to be stronger, and the repository's own test harness knocked it down.**

The original justification was that a weakness spread thinly across many topics is close to
*invisible* on a topic report — roughly four times more visible on the rule axis. That does not
survive contact with the real bank. `DETECTION.md` plants exactly such a weakness and runs both
diagnostics over the generated history: the rule axis finds it 100% of the time at 3,000 answers,
and **the topic axis also finds it, 100% of the time.** The reason is not mysterious. Rules are not
spread evenly over topics here, so most rules have some topic where they govern the majority of the
questions, and a rule weakness drags that topic to the bottom of the list.

What survives is narrower and still worth having. Studying the three weakest *topics* reaches only
**14% to 41%** of the questions governed by the planted rule, depending on history length. So the
topic report points at one affected subject, and the rule report names the cause that is also
costing marks in the four domains you were not sent to study. The rule axis is the more useful
readout because of what it *names*, not because the topic axis is blind.

| Claim | Status |
|---|---|
| The rule axis reliably surfaces a rule-level weakness | **holds** — 96% detection from ~300 answers, 6% false positive |
| A topic report cannot see that weakness | **false** — it sees it essentially always |
| Studying the weakest topics fixes the rule weakness | **false** — reaches 14–41% of the affected questions |

The numbers, their intervals and the method are in `DETECTION.md`, regenerated by
`python drill.py simulate --write`.

### What the diagnostic actually tells you

Each rule carries the **misapplication** — the rule people substitute for it — and a **scope note**
saying when it does *not* apply. Both matter. "Prevent beats detect" is only true when the stem asks
what addresses a weakness; if it asks about recovery or evidence, the ranking inverts, and treating
a scoped rule as universal is its own trap.

So a weak rule reports back as: the accuracy, the confidence interval, what you are probably doing
instead, where the boundary is, and the exact command to drill it.

### Costumes

`costumes` picks your weakest rule and serves one question from each domain it appears in. Same
reasoning, five completely different surfaces — segregation of duties as audit staffing, code
promotion, job scheduling, privileged access. Studying by domain actively hides these connections.

Costume answers are full scenario questions answered normally, so they go to `attempts.jsonl` as
real evidence — unlike the short-form games below.

### The study card

`principles --card` generates the reference sheet from the taxonomy, so it cannot drift from the
rules actually being tested. A copy lives at `cisa/study-guides/decision-rules-card.txt`; regenerate
it with `--out` after editing the taxonomy.

---

## Short-form games

```bash
python drill.py game coldread -n 10    # options hidden
python drill.py game autopsy -n 8      # why is each wrong option wrong
python drill.py game stats             # results so far
```

Both run off the existing question bank — no extra content needed — and both take a couple of
minutes, so they suit short bursts between longer sessions.

**Cold Read.** The stem appears with the options hidden. You say what the question is *asking for*
(first action / greatest risk / best control / best evidence / definition), then predict the answer
before seeing the choices. Targets the most common real failure on this exam: confidently answering
a question you misread. The read is auto-graded; the prediction is yours to self-assess.

**Autopsy.** The correct answer is given up front. The three explanations of why the *wrong* options
are wrong appear scrambled and unlabelled, and you match each option to its explanation. Fully
auto-graded. This teaches how the traps are built, which is the part that transfers to questions you
have never seen.

### These are kept out of your real stats, on purpose

Games write to `cisa/results/games.jsonl`, a **separate file** from `attempts.jsonl`. Nothing from a
game reaches your headline accuracy, item analysis, or the spaced-repetition scheduler.

A five-second answer is not the same evidence as a worked scenario, and mixing them would corrupt
both. It would also let you feel prepared on the strength of the easy half.

`game stats` shows accuracy per game, weakest topics, and — the most useful part — a **misread
table** showing the direction of your confusions: which question type you mistook for which. If
`risk -> control` keeps appearing, you are reading "what is dangerous here" as "what should be done
about it", and that single habit costs marks across every domain.

### An honest note on what these do and do not train

The CISA exam is mostly judgment under a messy scenario, not recall. These games sharpen the
substrate — knowing instantly what a question is asking, and how distractors are constructed — so
that working memory is free for the judgment. They are not a substitute for `drill` and `exam`, and
if game numbers climb while mock scores stay flat, believe the mock scores.

---

## Branching cases

```bash
python drill.py case                       # pick from the list
python drill.py case d1-one-exception      # play a specific case
python drill.py case --list                # what exists, and what you have attempted
python drill.py case --resume <id>         # continue a case in progress
python drill.py case --stats               # how your paths have gone
```

A case drops you into an engagement. You make five to eight decisions, the situation moves in
response, and **you find out how it went at the end** — not at each step.

It exists because a multiple-choice question cannot express two things the exam actually tests:
**sequential judgment**, where your first decision changes what you face next, and **graded
correctness**, where an option is defensible-but-worse rather than simply wrong. Options are scored
`best` / `defensible` / `poor`, and while you are playing you get only a neutral narration of what
happened. No verdict, no score counter, no reassurance — sitting with an uncertain choice is the
thing being trained.

Some options are **taints**: they fix the outcome regardless of what you do afterwards. Agreeing to
omit a finding is not recovered by answering the next three questions well. When one fires, the
debrief names the decision that decided it, which is the single most useful sentence the format
produces.

The debrief shows the path you walked, what the best option was at each node and why, where the
branches you did not take would have led, and the ending with its verdict. **Never a percentage** —
collapsing a path to one number throws away the part that teaches.

Three cases ship today: audit execution (D1), business resilience (D4), incident response (D5).
Format is documented in `cisa/cases/SCHEMA.md`. Case results go to `cases.jsonl`, not to
`attempts.jsonl` — a case is not a four-option question and letting it reach item analysis or the
scheduler would corrupt both.

---

## Calibration — did you know that you knew

```bash
python drill.py calibration                # the curve, the quadrants, the gap
python drill.py calibration --target 2027-01-15   # set a study horizon
```

Every drill, costume and exam answer asks for a confidence level as you answer it — `1` guess,
`2` unsure, `3` confident. Two keystrokes, and it captures something the rest of the tool cannot
reconstruct afterwards.

The reason is this table:

| | Correct | Wrong |
|---|---|---|
| **Confident** | genuinely known | **the quadrant that sinks people** |
| **Guess / unsure** | lucky — counted as learned, but it is not | known unknown, least dangerous |

Being confident and wrong reads as a win, and nothing else in the tool will ever bring that question
back to you as a problem. `calibration` lists every one of them, most recent first, with the topic
and the governing decision rule.

The reverse case is quieter: a guessed-correct answer currently earns the same spaced-repetition
credit as a reasoned one, so the scheduler pushes it further away exactly when it should not. Those
are listed too.

**The overconfidence gap** is accuracy when confident minus accuracy when *not* confident, reported
with a 95% interval **on the difference**. If that interval includes zero, the tool says so plainly —
"not yet evidence that your confidence tracks whether you are right" — rather than showing you a
small number that reads like a finding. It is not called a score and there is no single number
summarising your calibration, because collapsing this to one figure throws away the actionable part.

Everything breaks down **by decision rule as well as by topic**. "You are overconfident specifically
on evidence-quality questions" is far more useful than a global figure.

Answers logged before this feature existed load as unrated and are counted separately. They are
never backfilled — an invented confidence is worse than a missing one.

**Note the deliberate omission.** Confidence does not yet influence the scheduler, even though using
it to stop a guessed-correct answer earning a 35-day interval is the obvious next application.
Capture first, prove the signal, then touch a working scheduler.

---

## Reading your stats

```bash
python drill.py stats              # top 12 weakest topics
python drill.py stats --all        # every topic
python drill.py stats --domain 5   # one domain
```

You get lifetime accuracy, how much of the bank you have touched, per-domain accuracy with exam
weights shown, per-topic accuracy weakest first, and your most-missed individual questions.

Low coverage with high accuracy usually means you have been re-drilling the same comfortable subset.

---

## Item analysis

```bash
python drill.py items                    # bank health, weak topics, suspect questions
python drill.py items --domain 5
python drill.py items --min-attempts 8   # raise the bar before an item gets statistics
python drill.py items --all
```

This one is about the **questions**, not you. Standard psychometrics assumes many examinees taking
one test; here it is one examinee over many sessions, so the statistics are adapted:

- **Difficulty (p-value)** — proportion answered correctly, reported with a **Wilson confidence
  interval**. This matters: 2 out of 2 is not 100%, it is somewhere between 34% and 100%. The
  interval width tells you whether a number is worth acting on.
- **Discrimination** — normally compares high scorers against low scorers. Here it correlates each
  item against your score on the *other* items in the same session, which avoids an item inflating
  its own correlation. Needs at least 6 attempts across 3 sessions before it reports anything.
- **Distractor analysis** — how often each option was chosen.

Flags you may see, and what they mean:

| Flag | Meaning |
|---|---|
| `TOO_EASY` | you always get it right; it carries no information and is wasting a slot |
| `TOO_HARD` | almost always missed — either a genuine gap or a badly written item |
| `NEG_DISCRIMINATION` | you get it right on bad sessions and wrong on good ones, which usually means the item is ambiguous or mis-keyed |
| `KEY_CHALLENGED:C` | a distractor is chosen more often than the keyed answer — check for ambiguity |
| `DEAD_OPTION:CD` | nobody ever picks those options; they teach nothing |
| `PERSISTENT_MISS` | three or more consecutive misses — this one is about you, not the question |
| `THIN_DATA` | not enough attempts to say anything yet |
| `NEVER_SERVED` | in the bank but never drilled |

Topics are ranked by the **lower bound** of the confidence interval rather than by raw accuracy.
That is deliberately conservative: it surfaces both genuinely weak topics and under-tested ones, and
drilling an under-tested topic is the right response either way because it resolves the uncertainty.

If an item is flagged `NEG_DISCRIMINATION` or `KEY_CHALLENGED`, read it again with fresh eyes. Often
the question is genuinely ambiguous and worth rewriting — tell me and I will fix it.

### How much to trust these flags

Less than the rest of the tool, and `DETECTION.md` says so with numbers.

The harness plants a question that measures nothing — answered at chance regardless of ability — and
asks whether `needs_rewrite()` flags it. At 3,000 answers it catches 55% of them **and also fires on
88% of learners with nothing planted**. A miskeyed question does better on detection, 98%, with a
37% false-positive rate. Both are outside the threshold this project uses for a trustworthy check.

Note the direction of the problem: the false-positive rate *rises* with more history rather than
falling, which is the signature of thresholds that fire on ordinary variation once samples get large,
not of a check that merely needs more data.

Read a flag as "worth a look" rather than as a verdict. On a bank this size, most of what it
highlights at high volume will be fine.

---

## Other commands

```bash
python drill.py list --domain 5    # question count per outline topic, gaps visible
python drill.py validate           # check the bank for problems
python run_tests.py                # all 364 tests
python run_tests.py -v exam        # verbose, one suite
```

---

## Adding question batches

Questions are plain data files in `cisa/questions/`, deliberately separate from the code. Add a new
file per batch; the loader picks up every `.json` file in that folder automatically.

Naming convention: `d<domain><section>-<slug>.json`, e.g. `d1a-planning.json`.

```json
{
  "meta": {
    "cert": "CISA",
    "domain": "1",
    "section": "A",
    "batch": "d1a-002",
    "created": "2026-08-01",
    "origin": "Original questions. No third-party question content reproduced."
  },
  "questions": [
    {
      "id": "cisa-d1a-027",
      "topic": "Risk-Based Audit Planning",
      "difficulty": "medium",
      "stem": "... ending in a question mark, or in a colon for a completion stem:",
      "options": { "A": "...", "B": "...", "C": "...", "D": "..." },
      "answer": "C",
      "why_correct": "Why the keyed answer is right.",
      "why_wrong": {
        "A": "Why A is wrong.",
        "B": "Why B is wrong.",
        "D": "Why D is wrong."
      }
    }
  ]
}
```

`domain`, `section` and `cert` can live in `meta` (applying to the whole file) or on individual
questions, which override. `topic` must match a topic string in `cisa/outline.json` exactly — that
check is what stops tags from drifting as the bank grows.

**Always run `python drill.py validate` after editing.** It fails on: duplicate IDs, missing or empty
options, an answer key outside A–D, duplicate option text, a missing explanation for the correct
answer or any distractor, unknown keys in `why_wrong`, and topics that are not in the outline. It
warns without failing on stems that lack a judgment word or that are neither a question nor a
completion stem.

YAML batches also work if you happen to have PyYAML installed, but JSON is the format everything
ships in so that the tool never needs an install step.

### House style for writing questions

- Judgment stems, not recall: BEST, MOST, FIRST, GREATEST, PRIMARY, LEAST, STRONGEST.
- Four options, one defensible answer, three plausible distractors. A distractor that is obviously
  silly teaches nothing — and `items` will eventually flag it as a dead option.
- Write from the auditor's seat: what should the *auditor* be most concerned about, or recommend.
- Distractors should be things that are true but not responsive, or right for a different question.
- Explain every wrong answer. The distractor explanations carry more learning value than the stem.
- Vary the answer key. The bank currently sits at A 25% / B 24% / C 26% / D 24% across 386 questions,
  so there is no positional pattern to exploit.
- **Never reproduce ISACA, QAE or any other copyrighted questions.** Everything here is original.

---

## Your results log

`cisa/results/attempts.jsonl` is one JSON object per line, appended and never rewritten:

```json
{"ts": "2026-07-26T22:49:18-04:00", "session": "1904fd39", "question_id": "cisa-d5a-009",
 "cert": "CISA", "domain": "5", "section": "A", "topic": "Identity and Access Management",
 "chosen": "A", "answer": "C", "correct": false, "seconds": 41.2, "mode": "smart",
 "confidence": "confident"}
```

Greppable and easy to analyze directly if you want to do your own cuts in pandas. `mode` is `smart`,
`due`, `weakest`, `random` or `exam`. `confidence` is `guess`, `unsure`, `confident`, or empty for
rows written before that feature existed. Deleting the file resets all progress; a corrupted line is
skipped rather than breaking the whole log.

Saved mock exams live in `cisa/results/exams/<id>.json` and can be deleted individually. Short-form
games go to `games.jsonl` and cases to `cases.jsonl`, both deliberately separate from this file.

---

## Current status

| | |
|---|---|
| Question bank | **386 original questions**, all 5 domains, all 60 outline topics covered |
| Domain 1 — Auditing Process (18%) | 67 questions, 10 topics, study guide |
| Domain 2 — Governance & Management (18%) | 67 questions, 11 topics, study guide |
| Domain 3 — Acquisition & Development (12%) | 68 questions, 8 topics, study guide |
| Domain 4 — Operations & Resilience (26%) | 95 questions, 16 topics, study guide |
| Domain 5 — Protection of Info Assets (26%) | 89 questions, 15 topics, study guide |
| Difficulty bands | easy 52 / medium 243 / hard 51 / expert 40; selectable, strict, with a ramp |
| Mock exams | full 150q / 240min, blueprint-weighted, resumable |
| Branching cases | 3, with graded options, taints and a path debrief |
| Calibration | confidence captured per answer; curve, quadrants, gap with an interval |
| Item analysis | difficulty, discrimination, distractor quality — see the caveat above |
| Detection report card | `DETECTION.md`, generated by `drill.py simulate`; scores the diagnostics against planted weaknesses |
| Games | Cold Read and Autopsy, logged separately from real stats |
| Confusable pairs | 29 documented, 69 questions mapped, **no gaps** |
| Decision rules | 23 documented, 308 of 386 questions mapped, all multi-domain |
| Web app | React + TypeScript + Recharts, built output committed; server is stdlib, localhost only |
| Profiles | separate histories over a shared bank |
| Tests | **364**, all passing; `validate` clean with no warnings |

### Mock exam headroom

A 150-question mock draws to the blueprint, so the heavy domains burn through their pools fastest:

| Domain | Weight | Drawn per mock | Pool | Mocks before questions repeat |
|---|---|---|---|---|
| 1 | 18% | 27 | 67 | 2.5 |
| 2 | 18% | 27 | 67 | 2.5 |
| 3 | 12% | 18 | 68 | 3.8 |
| 4 | 26% | 39 | 95 | 2.4 |
| 5 | 26% | 39 | 89 | 2.3 |

Every domain now supports at least two non-overlapping mocks, and no topic anywhere in the bank sits
below four questions. Three or four mocks of headroom in the heavy domains would be better still.

## Next up

1. **Repair item analysis, or narrow what it claims.** `DETECTION.md` shows both of its flags
   outside the trustworthy threshold, with false positives that *rise* as history grows — 88% and
   37% at 3,000 answers. Either the thresholds need to scale with sample size, or the flags need to
   be presented as hints rather than findings. This is now the weakest thing in the repository, and
   it is only known because the harness measured it.
2. **Re-run the harness against the enlarged bank.** `DETECTION.md` was generated against 346
   questions and 23 rules; the bank is now 386 with the expert band mapped in. The asymmetry finding
   is unlikely to reverse, and the sample-size thresholds may move.
3. **Let confidence inform the scheduler.** A guessed-correct answer should not earn a 35-day
   interval. Check 7 shows the confidence signal is trustworthy from about 300 answers, so this is
   no longer blocked on evidence — only on someone building it.
4. **More branching cases.** Three proves the format; it is not yet a library.
5. **More mock-exam headroom in D4 and D5.** Both now clear two non-overlapping mocks; three or four
   would be better.
6. **A retention model (FSRS)** — deliberately deferred. Personalised parameters need on the order
   of a thousand reviews to fit against, and defaults would just be Leitner with extra arithmetic.
7. **Stand up `cpa/`** once CISA is passed — verify the current AICPA blueprints first, since the
   exam structure changed under CPA Evolution, and CPA includes task-based simulations this
   multiple-choice engine does not model.

### Checking whether the games actually help

`cisa/confusable-pairs.json` maps each documented confusion to the bank questions that turn on it.
That mapping exists so the question can eventually be answered with data: does drilling a pair
precede improved accuracy on the questions that depend on it?

Worth being honest about the limit — one learner, everything confounded with whatever else was
studied that week. It would catch a game that does nothing. It would not prove one that helps.
