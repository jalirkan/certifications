# Synthetic learners and the detection report card — handoff brief

For a coding agent with a terminal. Read `CLAUDE.md` first.

This is the piece that lets the project make claims about itself.

---

## 1. Why

The tool makes two claims that nobody has tested:

> "Reporting weakness by **decision rule** finds problems that a topic report hides."
>
> "Item analysis identifies **badly written questions**."

Both are plausible. Neither is established. And they cannot be established from Justin's own study
history, because with real data you never know the right answer in advance — if the tool reports a
weakness in `evidence-quality`, there is no independent way to confirm he actually has one.

**Synthetic data inverts that.** Generate a study history for a learner whose weaknesses you planted
yourself, run the diagnostics, and check whether they found what you put there. Now you know the
answer before you look.

This is the same move as `audit-automation-lab` (planted anomalies in synthetic ledgers) and
`itgc-lab` (planted violations in synthetic enterprises). It is the pattern this repository should
have used from the start, and it is the single strongest thing the project can show a reader.

---

## 2. What exists

| | |
|---|---|
| Diagnostics to score | `drillkit/principles.py`, `stats.py`, `itemanalysis.py`, `scheduler.py`, `calibration.py` |
| Attempt record | `store.Attempt` — 13 fields, `confidence` may be `""` |
| Real bank | 298 questions, 23 rules, 60 topics — use it, do not invent a fake bank |
| Precedent | `tests/test_principles.py::TestDiagnosisFindsPlantedWeakness` |

**Read that precedent before designing anything.** It already plants a rule-level weakness and
asserts the principle axis ranks it first while the topic axis stays flat. It is the harness in
miniature, hardcoded and single-seed. Your job is to generalise it into something that reports a
rate rather than asserting a single draw.

`drillkit/calibration.py` is being built in a separate stream right now. **Design the scorer so
calibration checks slot in, but do not block on it** — build the harness against the diagnostics that
exist and add the calibration checks when that work lands.

---

## 3. The learner model

A synthetic learner is a small, explicit specification. Something close to:

```
baseline          probability correct on a question with no planted weakness
weaknesses        [(axis, key, ability)]  axis in {"principle", "topic", "domain"}
confidence        how reported confidence relates to actual correctness
pace              answers per day, and over how many days
repeats           whether questions are re-served (needed for scheduler and item analysis)
seed              everything is seeded; a run must be exactly reproducible
```

Draw against the **real question bank** so topic and rule structure is realistic — a rule genuinely
spread across four domains, topics with three questions and topics with eleven. A synthetic bank
would let you accidentally design away the very sparsity that makes detection hard.

Emit real `store.Attempt` rows through the real writer. If the harness constructs dictionaries by
hand it will drift from the schema and stop measuring the actual system.

---

## 4. What to score

Each check is a yes/no question with a known answer. Suggested starting set:

| # | Plant | Check | Diagnostic |
|---|---|---|---|
| 1 | Weak on one decision rule | Is it in the top 3 of `principles.weakest()`? | principle axis |
| 2 | Weak on one topic | Is it the weakest topic in `stats.by_topic()`? | topic axis |
| 3 | Weak on one rule, spread thin | Rule axis ranks it; topic axis does not | **the asymmetry claim** |
| 4 | A question with no discrimination | Does `itemanalysis.needs_rewrite()` flag it? | item analysis |
| 5 | A miskeyed question (strong learners do worse) | Flagged? | item analysis |
| 6 | Persistent misses on specific questions | Do they come back sooner than known ones? | scheduler |
| 7 | Overconfident learner | Does the gap show? Are planted confident-wrongs listed? | calibration |
| 8 | A question whose authored label is wrong | Is the authored-versus-empirical disagreement flagged? | difficulty labels, if that work has landed |

Check 8 is a late addition. `DIFFICULTY-BRIEF.md` adds a comparison between each question's
authored `easy`/`medium`/`hard` label and its measured p-value, to find labels that do not match how
the question behaves. That is a diagnostic like any other and it makes a claim, so it belongs here:
generate a learner for whom a question labelled `easy` is reliably missed, and check the
disagreement surfaces. If that work has not shipped yet, skip the check rather than waiting.

Check 3 is the one that matters most. It is the justification for the entire principle axis, and it
is currently supported by one test at one sample size with one seed.

---

## 5. The two things that make this real

Everything above could be built in a way that always reports success. Two additions prevent that,
and they are the point of the exercise rather than extras.

**A negative control.** Generate learners with **no planted weakness at all** and run the same
checks. Every "detection" is now a false positive. A diagnostic that flags a weakness in a uniformly
average learner is worse than useless — it will send Justin to study something that is not wrong
with him. Report the false-positive rate beside the detection rate, always. A detection rate without
one is not evidence.

**A sample-size sweep.** Run each check at 100, 300, 1,000 and 3,000 attempts. The output is a
curve, and the curve answers the question that actually blocks this project:

> How many questions does Justin have to answer before this diagnostic tells him something true?

That converts "we need more data" from a feeling into a number, per diagnostic. It is likely to be
the most useful single output of this work, and it may well show that some diagnostics need more
data than he will ever generate — which is a real finding and must be reported as one.

Run many seeds per configuration (start at 200) and report the rate with a **Wilson interval**, using
the existing `itemanalysis.wilson_interval`. A single seed is a coin flip. `CLAUDE.md` §3.6 applies
to the harness's own statistics exactly as it applies to the learner's.

---

## 6. Non-negotiable

1. **Never write to `cisa/results/`.** Temp directories or an explicit output path only. `CLAUDE.md`
   §3.13 — that is real study history and there is very little of it.
2. **Synthetic rows must be unmistakable.** Distinct session prefix, distinct profile, and the
   harness should refuse to run if pointed at a path containing real attempts. A synthetic row that
   reaches the real log is unrecoverable: nothing in the record distinguishes it afterwards.
3. **Detection rates always carry an interval, and never appear without the matching
   false-positive rate.**
4. **Do not tune a diagnostic to pass the harness.** This is the whole ethos and the easiest rule to
   break by accident. If the principle axis fails check 3 at realistic sample sizes, that is the most
   valuable finding available and it goes in the report card as a failure. Adjusting thresholds until
   the number looks good converts an instrument into a decoration. Raise it and stop; do not fix it
   in the same change.
5. **Never a single headline "accuracy" for the tool.** Report per-check, per-sample-size. Collapsing
   this to one number is the same mistake ruled out for cases in `CLAUDE.md` §3.5.
6. **`drillkit/`, `drill.py`, `serve.py` stay standard-library only.**

---

## 7. Output

A generated, committed markdown report — `DETECTION.md` at the repository root, so it is visible to
anyone browsing the repo. Per check: what was planted, detection rate with interval, false-positive
rate with interval, and the sample size at which detection becomes reliable.

Write the interpretation in plain language. "The decision-rule axis identifies a planted weakness in
94% of runs (CI 90–97%) once roughly 600 answers exist; below 300 answers it is no better than the
topic axis" is the sentence this whole piece of work exists to be able to write — or to be unable to
write, honestly.

Wire it to `python drill.py simulate` with flags for seeds, sample sizes and which checks to run, and
keep the full sweep out of `run_tests.py` — a handful of fast seeded cases belong in the suite, the
200-seed sweep does not.

---

## 8. Done

- A learner spec, a generator, and a scorer, all seeded and reproducible
- All checks in §4 that do not depend on unlanded calibration work
- Negative control on every check, reported beside detection
- Sample-size sweep with the "trustworthy from N answers" figure per diagnostic
- `DETECTION.md` generated and committed, readable by someone who has never seen the repo
- `python run_tests.py` green, `python drill.py validate` clean
- `cisa/results/attempts.jsonl` byte-identical before and after a full sweep — verify this explicitly

---

## 9. How to work

- **Argue with this brief.** The learner model in §3 is the part most likely to be wrong; you will
  learn things building it that are not knowable from here. Independence between questions is a
  simplification, and if it distorts the result, say so.
- **Report failures as findings, not as bugs to hide.** A diagnostic that does not work is the most
  useful thing this harness can discover. Justin would rather know.
- **Ask before**: changing any diagnostic module, touching `cisa/results/`, or altering `CLAUDE.md` §3.
