# Branching case format

A case is a small directed acyclic graph of audit decisions. You are dropped into an engagement,
you choose, the situation moves, and you find out how it went **at the end** — not at each step.

This format was written by authoring three cases first and then formalising what they needed, rather
than designed up front. If a rule below looks arbitrary, check the "why" — most of them exist because
writing the first case exposed a problem.

Validate with `python drill.py validate`. Zero errors is the bar; warnings are usually real.

---

## The three things that make this not a multiple-choice question

**1. Option quality is graded, not binary.** `best` / `defensible` / `poor`.

Real audit judgment is rarely right-or-wrong. A defensible option is one a competent auditor could
choose and defend — slower, more expensive, or slightly less complete, but not a mistake. That
gradation is precisely what a four-option MCQ cannot express, and it is most of the reason this
format exists.

**2. Feedback is deferred.** Each option carries a neutral `consequence` shown as you move, and a
`why` that is held back for the debrief.

If the app told you "that was poor" at each step, a case would be a series of MCQs with narration.
The thing being trained is living with a choice whose cost only appears two steps later — which is
how bad audit judgment actually plays out.

**3. Some choices are unrecoverable.** An option may carry a `taint` that fixes the outcome no matter
what follows.

This was discovered, not planned. In the first case, agreeing to omit a finding from the report is
not something you recover from by answering the next question well — but the graph would have
awarded whatever ending the last node produced. Taints fix that.

---

## File layout

One case per file in `cisa/cases/<id>.json`. Filename must match the `id`.

```jsonc
{
  "id": "d5-encrypted-share",          // matches filename
  "title": "The Encrypted Share",
  "domain": "5",
  "section": "B",                      // optional
  "topics": ["..."],                   // must match cisa/outline.json exactly
  "principles": ["contain-first"],     // must exist in cisa/principles.json
  "minutes": 12,                       // rough playing time
  "origin": "Original scenario ...",   // provenance, same rule as the question bank

  "opening": "Scene-setting shown once before the first decision.",

  "taints": {                          // optional. DECLARATION ORDER IS PRECEDENCE.
    "suppressed": "end-failed",        // worst first — wins if a path collects both
    "independence-lost": "end-compromised"
  },

  "nodes": { "start": { ... } },       // a node named "start" is required
  "endings": { "end-strong": { ... } }
}
```

### Node

```jsonc
"the-omission-request": {
  "situation": "What you now know, or what just happened.",
  "prompt": "The actual question. What do you do?",
  "options": [ ... ]                   // at least 2, exactly one marked "best"
}
```

### Option

```jsonc
{
  "key": "B",                          // unique within the node
  "text": "What the auditor does.",
  "quality": "best",                   // best | defensible | poor
  "next": "backup-evidence",           // a node id OR an ending id
  "consequence": "Neutral narration of what happens. NO verdict here.",
  "why": "The teaching. Shown only in the debrief.",
  "taint": "suppressed"                // optional; must be declared in taints
}
```

### Ending

```jsonc
"end-strong": {
  "title": "Short label",
  "verdict": "strong",                 // strong | acceptable | weak | failed
  "narrative": "How the engagement turned out.",
  "why": "What the path got right or wrong, and why it mattered."
}
```

Prefix endings with `end-` so they are visually distinct from nodes when reading a `next`.

---

## Rules the validator enforces

**Errors** — the case will not load cleanly:

- required top-level fields present
- `topics` all exist in `outline.json`; `principles` all exist in `principles.json`
- a `start` node exists
- every node has `situation`, `prompt`, and at least **two** options
- every option has all six required fields, a valid `quality`, and a `next` that resolves
- option keys unique within a node
- **every node has exactly one option marked `best`** — every decision needs a defensibly correct answer
- every `taint` used by an option is declared; every declared taint points at a real ending
- every ending has all four fields and a valid `verdict`
- **no cycles.** A decision you can return to unchanged is not a decision, and a cycle lets a case run forever
- case ids unique across files

**Warnings** — usually a real authoring mistake:

- a node unreachable from `start`
- an ending unreachable by any path *and* not the target of a taint
- more than one option marked `best`
- a declared taint no option applies
- `id` does not match the filename

---

## Authoring notes

**Length.** Five to eight nodes. Longer stops feeling like a decision chain and starts feeling like
a novel. Aim for 10–15 minutes.

**Every node needs a real `best`.** If you cannot name the defensibly correct action, the decision
is not well posed — rewrite the node rather than picking the least-bad option and calling it best.

**Wrong-but-plausible options should not fail immediately.** Route them somewhere that fails two
steps later. A poor choice at node 1 that dead-ends at node 2 teaches nothing; one that quietly
narrows your options until the ending is weak teaches the thing MCQs cannot.

**Make recovery possible, usually.** Real audits recover from bad calls. Most poor choices should
still be able to reach an acceptable outcome if the auditor handles the aftermath well — that
asymmetry between recoverable and unrecoverable errors is itself the lesson. Reserve taints for
decisions that genuinely cannot be walked back: suppressing a finding, participating in what you
will later audit, misstating a timeline.

**`consequence` must not judge.** "You disconnect. The share drops. The security lead arrives asking
pointed questions" is right. "You disconnect, which was a mistake" is not — that belongs in `why`.

**Write the `why` for someone who chose it.** They had a reason. Name the reason, then say what it
missed. "Understandable instinct, and wrong on two counts" lands; "this is incorrect" does not.

**Scoped rules are the best material.** The strongest decisions in these cases are ones where a rule
the learner knows is genuinely right *in general* and wrong *here* — containment comes first, but not
when you are the auditor rather than the responder. That is where `principles.json` scope notes and
these cases meet.

---

## What the debrief is built from

`drillkit/cases.py` provides `score_path()`, which returns a profile rather than a score:

```
decisions, counts { best, defensible, poor }, taints[],
ending, verdict, overridden, principles[]
```

**Deliberately not a percentage.** A path is a set of judgments plus an outcome, and collapsing that
to one number throws away the part that teaches. "You reached a strong ending with two defensible
choices and one poor one" is information; "73%" is not.
