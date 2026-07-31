# Confidence capture and calibration — handoff brief

For a coding agent with a terminal. Read `CLAUDE.md` first.

Small feature, and the only one on the roadmap with a **deadline**. Everything else can be built
whenever. This one has to exist before the answers accumulate, because confidence cannot be
recovered retrospectively — every question answered between now and shipping it is permanently
unlabelled.

---

## 1. Why

The tool currently measures whether an answer was **right**. It does not measure whether the learner
**knew** it was right. Those are different, and the gap between them is where exam failures live.

Four states, and only two are currently visible:

| | Correct | Wrong |
|---|---|---|
| **Confident** | genuinely known | **the dangerous quadrant** — you will never revisit this |
| **Unsure / guess** | lucky — not learned, but counted as learned | known unknown, least dangerous |

The top-right cell is the one that sinks people. You are confident, you are wrong, and nothing in
the current system will ever bring that question back to you as a problem. It reads as a win.

The bottom-left is the quieter version: a guessed-correct answer currently earns the same
spaced-repetition credit as a reasoned one, so the scheduler pushes it further away precisely when
it should not.

---

## 2. Capture

**Three-way, mandatory, taken with the answer.** Decided; do not substitute a slider or a numeric
percentage. People cannot produce calibrated numbers without training, and an optional control gets
skipped exactly when the learner is tired — which is when the data is most interesting.

```
guess      | no better than picking
unsure     | leaning one way, could not defend it
confident  | would defend this in a review
```

**Interaction:** the answer and the confidence should feel like one action, not two screens. In the
CLI, a second keystroke immediately after the answer key. In the browser, adjacent controls with
keyboard shortcuts — `A`–`D` then `1`/`2`/`3`, or whatever proves natural once you build it.

If the learner has to think about the *control*, the friction will kill the data. Time it: two
keystrokes should take under a second.

**Storage:** a `confidence` field on the `Attempt` record in `drillkit/store.py`. It currently has
twelve fields and no confidence.

- Values: `""` | `"guess"` | `"unsure"` | `"confident"`
- **Empty string means not recorded** — every existing row in `attempts.jsonl` predates this feature
  and must keep loading cleanly. This is real personal study history; do not migrate or rewrite it.
- Applies to drills, costumes and exams. **Not** to Cold Read or Autopsy — those already have a
  self-report and are logged separately.

---

## 3. What to report

**Calibration curve.** For each confidence level, accuracy with a Wilson interval — `CLAUDE.md` §3.6
applies here as everywhere. Well calibrated looks like a rising line; the interesting failure is a
flat one, which means the learner's confidence carries no information.

**The dangerous quadrant, as a list.** Every question answered `confident` and wrong, most recent
first, with the topic and the governing decision rule. This is the single most actionable output of
the feature and it should be reachable in one click from the dashboard.

**Lucky guesses.** Answered `guess` or `unsure` and correct. Not failures — but not learned either,
and currently indistinguishable from mastery.

**Overconfidence gap.** One number: accuracy when confident, minus overall accuracy. Near zero means
confidence is not discriminating. Report it with its interval and gate it on a minimum sample, and
do not dress it up as a score.

Break all of the above down **by decision rule** as well as by topic, using
`drillkit/principles.py`. "You are overconfident specifically on evidence-quality questions" is a
far more actionable sentence than a global figure.

---

## 4. Study horizon

Add an optional **target date** per profile, stored alongside results. Justin's working assumption
is **roughly six months out**, unbooked.

Use it for **coverage projection only**, not retention forecasting:

> At your current pace of N answers/day, you will reach 5 attempts per question in X days —
> Y days before your target.

That is honest arithmetic over the attempt log. **Do not build a retention forecast yet.** That
needs the FSRS work, which is deliberately deferred until there are enough reviews to fit and test
against. A decay curve drawn from published defaults would look authoritative and mean nothing.

---

## 5. Non-negotiable

1. **Existing rows must keep loading.** Missing `confidence` reads as `""`. Add a test that loads a
   record without the field.
2. **Never a "calibration score".** Report the curve, the gap, and the lists. Collapsing this to one
   number is the same mistake `CLAUDE.md` §3.5 rules out for cases.
3. **Wilson intervals on every rate**, gated on minimum sample. With a handful of answers per
   confidence level, all three cells are noise and must visibly read as noise.
4. **Do not change the scheduler in this piece of work.** Using confidence to stop a guessed-correct
   answer from earning a long interval is the highest-value application of this data and it is
   explicitly a later phase — capture first, prove the signal, then touch a working scheduler. Same
   reasoning as `CLAUDE.md` §3.15.
5. **`drillkit/`, `drill.py`, `serve.py` stay standard-library only.**

---

## 6. Done

- Confidence captured on every drill, costume and exam answer, in both front ends
- Two keystrokes, under a second, measured not assumed
- `attempts.jsonl` rows written before this feature still load and still appear in every report
- Calibration curve, dangerous-quadrant list, lucky-guess list, overconfidence gap — all with
  intervals, all available by rule as well as by topic
- Target date settable per profile; coverage projection shown; no retention forecast
- `python run_tests.py` green, `python drill.py validate` clean

---

## 7. How to work

- **Argue with this brief**, particularly on the interaction. Two keystrokes per question across
  1,500 answers is the whole risk of this feature — if it feels heavy when you build it, say so and
  propose better rather than shipping something that will be resented.
- **Ask before**: changing the `Attempt` schema beyond adding this field, touching the scheduler,
  or altering anything in `CLAUDE.md` §3.
