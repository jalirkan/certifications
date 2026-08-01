# Expert-band questions — authoring brief

> **Status: built 2026-07-31.** All 40 questions written, and the per-domain split in §3 was hit
> exactly: D1 7, D2 7, D3 5, D4 11, D5 10. Bank went 346 → 386.
>
> - Seven new files — `cisa/questions/{d1a,d1b,d2a,d2b,d3,d4,d5}-expert.json`.
> - Bands now read easy 52 / medium 243 / hard 51 / **expert 40**. `validate` is clean.
> - §3's floor is cleared: 40 supports a 20-question expert session bank-wide, and D4 and D5
>   each support a domain-filtered one.
> - No existing question was relabelled — the §3 prohibition held, and `hard` is still 51.
>
> **The body below is now stale in one place and is left as written.** The opening note and §1 say
> the band is empty and that the interface says so. Both were true when the brief was handed over;
> neither is true now. The counts in §1 (346 across three bands) describe the pre-batch bank and are
> the baseline this work was measured against, so they are worth keeping rather than overwriting.

**For a Cowork session.** This is content work: no build, no install, no test loop.
Read `CLAUDE.md` first — §3 rules 1–5 and the house-style note at the end govern everything here.

The engine side is already done. `expert` exists in the vocabulary, validates, filters strictly,
sorts last in ramp mode, and appears in the Drill tab of both front ends. The band is **empty**, and
the interface currently says so. Your job is to fill it.

---

## 1. Why this band exists

The bank has 346 questions in three authored bands: easy 52, medium 243, hard 51. There is no
question that a competent, well-prepared candidate would find genuinely difficult — `hard` mostly
means "more moving parts", not "requires judgement at a boundary".

`expert` is for the questions that separate someone who knows the material from someone who can
*apply* it when the material points two ways at once.

**It is not "hard plus one more clause".** Length is not difficulty. A question is not expert
because the scenario is long, the vocabulary is obscure, or the arithmetic is fiddly. Those make
questions tedious, and tedious questions teach nothing.

---

## 2. What makes a question expert, concretely

Use at least one of these four. The best questions use two.

**1. A scoped rule at its boundary.** `cisa/principles.json` holds 23 decision rules, and each
carries a `scope` note saying when the rule does *not* apply. A rule the learner has correctly
internalised, applied in the one situation where it is wrong, is the single richest source of
expert questions in this repository. Read the `scope` fields and write to them.

> Containment comes first in incident response — but not when you are the auditor rather than the
> responder, because participating destroys your independence over the very thing you will audit.

**2. Two defensible options separated by one condition in the stem.** Both answers are things a
competent auditor might do. A specific fact in the scenario — a date, a reporting line, a contract
clause, who commissioned the work — makes exactly one of them correct. The distractor explanation
must name that fact.

**3. The textbook answer is wrong here.** The option that best practice would normally endorse is
defeated by a stated constraint. This is the hardest kind to write honestly: the constraint must be
in the stem, unambiguous, and sufficient. If a reader can reasonably still defend the textbook
answer, the question is broken, not expert.

**4. Two domains at once.** A question that requires holding, say, a D4 recovery objective against
a D2 governance obligation. Real engagements do not respect the blueprint's boundaries.

**Anti-patterns — these are not expert, they are bad:**

- Trick wording, double negatives, "which is NOT least likely"
- An answer that turns on a number nobody would memorise
- Three plausible options and one absurd one
- Ambiguity dressed up as depth: if two options are genuinely defensible with no discriminator in
  the stem, the question is wrong
- Obscurity: a question about a standard nobody references is niche, not expert

---

## 3. How many, and where

Target **40 questions**, distributed by exam weight so a domain-filtered expert session is possible:

| Domain | Weight | Expert target |
|---|---|---|
| 1 — Auditing Process | 18% | 7 |
| 2 — Governance & Management | 18% | 7 |
| 3 — Acquisition & Development | 12% | 5 |
| 4 — Operations & Resilience | 26% | 11 |
| 5 — Protection of Assets | 26% | 10 |

Forty is enough for a 20-question expert session bank-wide, and enough that D4 and D5 support a
domain-filtered one. Fewer than about 25 and the band cannot fill a session, which is the state it
is in now.

**Do not relabel existing questions.** Write new ones. Promoting current `hard` questions would
invent a distinction nobody made and would empty a band that is already thin at 51.

---

## 4. File format

New files, so the existing ones stay reviewable:

```
cisa/questions/d1a-expert.json      cisa/questions/d4a-expert.json
cisa/questions/d1b-expert.json      cisa/questions/d4b-expert.json
...one per domain-section you write into...
```

Each file:

```jsonc
{
  "meta": {
    "domain": "1",
    "section": "A",
    "note": "Expert band. See EXPERT-BAND-BRIEF.md."
  },
  "questions": [
    {
      "id": "cisa-d1a-x01",
      "topic": "Risk-Based Audit Planning",
      "difficulty": "expert",
      "stem": "...",
      "options": {
        "A": "...", "B": "...", "C": "...", "D": "..."
      },
      "answer": "C",
      "why_correct": "...",
      "why_wrong": {
        "A": "...", "B": "...", "D": "..."
      }
    }
  ]
}
```

Rules the validator enforces, and will reject the batch for:

- **`id` unique across the whole bank.** Use an `x` marker: `cisa-d4b-x03`.
- **`difficulty` must be exactly `expert`.** Not `Expert`, not `very hard`.
- **`topic` must match `cisa/outline.json` character for character.** This is the most common
  failure. Copy the string; do not retype it.
- **Four options A–D, one `answer`, and a `why_wrong` entry for each of the other three.** Every
  wrong answer gets an explanation — they carry more teaching value than the stem.
- No two options with the same text; no empty fields.

---

## 5. House style, which matters more at this band

- **Judgement stems**: BEST, MOST, FIRST, GREATEST, PRIMARY, LEAST. Write from the auditor's seat.
- **Vary the answer key.** The bank currently sits at A 25% / B 24% / C 26% / D 25%, and that even
  spread is deliberate — do not put the correct answer on C every time because it "feels" right.
- **`why_wrong` is where the learning is.** For an expert question it must name the *specific* fact
  that defeats the option, not restate the correct answer. "This would be right if the review had
  been commissioned by management rather than the board" teaches; "this is incorrect" does not.
- **Never reproduce ISACA, QAE or any other copyrighted question.** Every item original. Not
  negotiable, and it applies to paraphrases too.

---

## 6. Before handing back

Run these two from the repo root. Both must be clean:

```
python drill.py validate
```

```
python drill.py drill --difficulty expert -n 10
```

`validate` fails on duplicate ids, bad answer keys, missing distractor explanations, unknown topics
and a difficulty outside the vocabulary. The drill command is the real test: if the band is
selectable and the questions read as genuinely harder than `hard`, the work is done.

Then say how many landed per domain, and flag any question you were not confident about rather than
shipping it quietly — a doubtful expert question is worse than a missing one, because it will be
answered wrong for the wrong reason and pollute the calibration data.

---

## 7. What is deliberately not your job

- **Do not touch `drillkit/`, `drill.py`, `serve.py` or `frontend/`.** The engine work is finished.
- **Do not compare authored labels against measured p-values.** That diagnostic is deferred and has
  a test harness waiting for it (`SIMULATION-BRIEF.md`, check 8).
- **Do not edit existing questions**, including their difficulty labels.
