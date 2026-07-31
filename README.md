# Certification study system

Offline study tooling for **CISA** now, **CPA** later. Pure Python standard library — nothing to
install, no network access at runtime.

## Two ways to use it

```bash
python serve.py      # web app — opens in your browser
python drill.py      # command line — same engine, same data
```

Both front ends read and write the same files, so you can drill in the browser and check `stats` in
the terminal. The web app is stdlib-only too: Python's own `http.server`, vanilla JavaScript, no
build step, no `node_modules`, no CDN. It binds to localhost only.

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
  run_tests.py              runs every test suite
  drillkit/                 the engine (certification-agnostic)
    loader.py                 question bank loading and validation
    scheduler.py              spaced-repetition-lite selection
    session.py                interactive drill loop
    stats.py                  accuracy roll-ups
    store.py                  append-only attempt log
    exam.py                   mock exam sampling, state and scoring
    examsession.py            timed exam runner and report
    itemanalysis.py           difficulty, discrimination, distractor quality
  tests/                    90 unit tests
  cisa/
    outline.json            ISACA exam content outline, all 5 domains (structural reference)
    study-guides/           topic checklists with notes and a status column
    questions/              question banks as JSON data, one file per domain-section
    results/
      attempts.jsonl          your answer log, append-only
      exams/                  saved mock exams, resumable
  cpa/                      empty sibling, same shape, for after CISA
```

The engine knows nothing about CISA specifically. Anything with an `outline.json`, a `questions/`
folder and a `results/` folder works — which is how CPA slots in later without a rewrite.

---

## Requirements

Python 3.7 or newer. Check with `python --version`. Nothing else.

If `python` is not recognized on Windows, try `py` instead, or install Python from python.org and
tick "Add python.exe to PATH".

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

Six screens, all reading the same data as the CLI:

- **Dashboard** — accuracy by domain with **confidence intervals drawn as whiskers**, so a wide bar
  visibly says "not enough evidence" instead of implying a precise percentage. Weakest rules and
  topics, with one-click drills into either.
- **Drill** — keyboard-first: `A`–`D` or `1`–`4` to answer, `Enter` to advance. When you answer,
  **each explanation attaches to the option it explains** rather than arriving as a list you have to
  map back yourself. The governing decision rule appears underneath.
- **Mock exam** — timer, flag-for-review, and a **question palette** showing answered / flagged /
  current at a glance so you can navigate a 150-question paper the way you would the real one.
  Resumable across browser restarts; the clock stops when you save.
- **Short form** — Cold Read and Autopsy, with the options genuinely withheld until you commit.
- **Decision rules** — the diagnostic, plus the generated study card.
- **Question bank** — item analysis and the confusable-pair reference.

**Answer keys never reach the browser before you commit.** A question arrives as stem and options
only; the key and the rationale come back in the response to your answer. Opening devtools during a
timed exam gets you nothing, and there is a test asserting it.

---

## Decision rules — the diagnostic that names the habit

```bash
python drill.py principles                 # which reasoning habits cost you marks
python drill.py principles --list          # the 22 rules and their coverage
python drill.py principles --card          # study card, generated from the taxonomy
python drill.py costumes                   # one rule, one question per domain
python drill.py costumes --principle prevent-first
python drill.py drill --mode principle -n 15   # target your weakest rules
```

CISA has an implicit value hierarchy that generates answers across every domain — risk assessment
before control selection, prevent beats detect, accountability cannot be outsourced, design evidence
is not operating evidence, contain before recover. Twenty-two of these rules are documented in
`cisa/principles.json`, each mapped to the bank questions it decides.

**Why this is a different question from `stats`.** A topic report says *study encryption*. A rule
report says *you reach for detective controls when the stem asks what prevents* — one habit, costing
marks in all five domains, fixable in an afternoon. It is also the only axis here that transfers to
questions that do not exist yet, which is the actual exam condition.

There is a measurable reason for it. A weakness spread thinly across many topics is close to
invisible on the topic axis and obvious on the rule axis — in simulation, roughly **four times more
visible**. That asymmetry is the whole justification for the feature, and there is a test that
measures it rather than asserting it.

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

---

## Other commands

```bash
python drill.py list --domain 5    # question count per outline topic, gaps visible
python drill.py validate           # check the bank for problems
python run_tests.py                # all 90 tests
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
- Vary the answer key. The bank currently sits at A 25% / B 24% / C 26% / D 25% across 292 questions,
  so there is no positional pattern to exploit.
- **Never reproduce ISACA, QAE or any other copyrighted questions.** Everything here is original.

---

## Your results log

`cisa/results/attempts.jsonl` is one JSON object per line, appended and never rewritten:

```json
{"ts": "2026-07-26T22:49:18-04:00", "session": "1904fd39", "question_id": "cisa-d5a-009",
 "cert": "CISA", "domain": "5", "section": "A", "topic": "Identity and Access Management",
 "chosen": "A", "answer": "C", "correct": false, "seconds": 41.2, "mode": "smart"}
```

Greppable and easy to analyze directly if you want to do your own cuts in pandas. `mode` is `smart`,
`due`, `weakest`, `random` or `exam`. Deleting the file resets all progress; a corrupted line is
skipped rather than breaking the whole log.

Saved mock exams live in `cisa/results/exams/<id>.json` and can be deleted individually.

---

## Current status

| | |
|---|---|
| Question bank | **292 original questions**, all 5 domains, all 50 outline topics covered |
| Domain 1 — Auditing Process (18%) | 60 questions, 10 topics |
| Domain 2 — Governance & Management (18%) | 60 questions, 11 topics |
| Domain 3 — Acquisition & Development (12%) | 60 questions, 8 topics |
| Domain 4 — Operations & Resilience (26%) | 60 questions, 16 topics |
| Domain 5 — Protection of Info Assets (26%) | 52 questions, 15 topics, plus full study guide |
| Mock exams | full 150q / 240min, blueprint-weighted, resumable |
| Item analysis | difficulty, discrimination, distractor quality |
| Games | Cold Read and Autopsy, logged separately from real stats |
| Confusable pairs | 29 documented, 63 questions mapped, 2 known bank gaps |
| Decision rules | 22 documented, 223 of 292 questions mapped, all multi-domain |
| Web app | stdlib `http.server` + vanilla JS, no build step, localhost only |
| Profiles | separate histories over a shared bank |
| Tests | 187, all passing |

The bank supports a full 150-question mock with no repetition, and roughly two non-overlapping
mocks before questions start recurring.

## Next up

1. Work through Domain 5 using the study guide, marking the status column as you go.
2. Sit a full mock to establish a baseline, then use the weighted gap analysis to direct study.
3. Study guides for Domains 1–4, matching the depth of the Domain 5 one.
4. Deepen the bank where `items` shows thin coverage or flags weak questions.
5. Close the two confusable-pair gaps — nothing in the bank currently tests **verification vs
   validation** or **FAR / FRR / CER**. `validate` warns about both.
5a. Look at the 16 judgment-worded questions that map to no decision rule. `validate` lists them.
   They are usually stems that promise judgment and test recall, which makes them the weakest
   CISA-style items in the bank and the first candidates for rewriting.
6. Pair Split and Sequence games, once there is evidence the first two are earning their keep.
7. Stand up `cpa/` once CISA is passed — verify the current AICPA blueprints first, since the exam
   structure changed under CPA Evolution.

### Checking whether the games actually help

`cisa/confusable-pairs.json` maps each documented confusion to the bank questions that turn on it.
That mapping exists so the question can eventually be answered with data: does drilling a pair
precede improved accuracy on the questions that depend on it?

Worth being honest about the limit — one learner, everything confounded with whatever else was
studied that week. It would catch a game that does nothing. It would not prove one that helps.
