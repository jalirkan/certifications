# Front end, second pass — handoff brief

For a coding agent with a terminal. Read `CLAUDE.md` first, then this.

Five pieces, independent, in the order they should ship. **B first.** Nothing here is a rewrite —
the front end built against `FRONTEND-BRIEF.md` stands, and this extends it.

---

## 1. Why, and what "ambitious" is allowed to mean here

The project's distinguishing features are already built and are close to invisible in the product:

- A detection report card that states **its own diagnostics fail** (`DETECTION.md`). It is a file.
  It is not in the app at all.
- Branching cases that name the decision that fixed the outcome four steps before the end. The
  debrief lists options node by node; **the graph they came from is never drawn.**
- Calibration built around the quadrant that reads as a win. It is a screen, but it is the last
  screen anyone finds.

So the work is not decoration. It is making the substance visible.

**The trap, stated so nobody walks into it in good faith.** `CLAUDE.md` §4 rules out gamification
permanently — no streaks, XP, badges, confetti, leaderboards, levels. "Make it impressive" is
exactly the instruction under which an agent adds a streak counter and calls it delight. Do not.
Every rule in `CLAUDE.md` §3 applies to everything below, and the honesty rules bind hardest
precisely where a surface is trying to look impressive.

---

## 2. What exists — do not rebuild

| | |
|---|---|
| Front end | Vite + React + TS + Recharts, ~5,600 lines in `frontend/src`, builds to `web/` |
| Screens | Dashboard, Drill, Exam, Cases, Calibration, Rules, Bank |
| Charts | `charts/` — Marimekko, rule dot-plot, trend, misread matrix, difficulty spread |
| Primitives | `ui/primitives.tsx` — Card, Stat, BarRow with Wilson whiskers, Callout, Seg |
| Design system | `styles.css`. Dark, restrained. Tokens for domain colours already exist |
| Dependencies | react, react-dom, react-router-dom, recharts. **Adding one needs a reason** |

The Python side is finished and dependency-free. Extending the API is fine; three of the five
pieces need it. Adding a dependency to `drillkit/` is not.

---

## 3. B — The case graph

**Ship this first.** It is the most visually striking thing available and it completes something
`CASES-BRIEF.md` §3 asked for that the current debrief only half-delivers: *"show the branches not
taken… seeing the tree, and where their thread diverged, is most of the teaching."*

### The data

The debrief currently returns only the nodes the learner walked. The full graph is in
`drillkit/cases.py` (`Case.nodes`, `Case.endings`, `reachable()`) and needs an API addition.

**It must remain debrief-only.** The graph reveals which option leads to `end-strong`; serving it
mid-run would leak the answer as surely as sending the key. Same rule as `CASES-BRIEF.md` §4.1,
same test discipline — add one asserting the graph is absent from every pre-debrief payload.

### The shape you are drawing

Measured, so the layout can be designed rather than guessed:

| Case | Nodes | Endings | Edges | Depth | Widest layer |
|---|---|---|---|---|---|
| d1-one-exception | 7 | 3 | 21 | 7 | 2 |
| d4-the-successful-test | 5 | 3 | 16 | 5 | 3 |
| d5-encrypted-share | 8 | 6 | 26 | 6 | 3 |

These are small, shallow, and nearly linear. **Do not reach for a graph library** — a layered
layout is about forty lines: assign each node its longest distance from `start`, group into layers,
order within a layer to reduce crossings, emit SVG. Cases are validated acyclic, so the layering
always terminates.

### What it must show

- The **walked path** lit, in sequence order.
- **Branches not taken**, greyed, still legible — they are the teaching.
- The **taint edge** marked distinctly. When an override fired, the graph should make the sentence
  "this was decided here" visually obvious, connecting the tainted choice to the ending it forced,
  *past* the ending the graph would otherwise have reached.
- **Endings coloured by verdict**, using the existing verdict tones.
- Hover or focus on any node showing its prompt; on any edge, the option text and its quality.

### Deliberate constraints

- Keyboard reachable. The rest of the app is keyboard-first and this must not be the exception.
- Legible at 900px wide without horizontal scrolling for a depth-8 case.
- No animation beyond a fade. `prefers-reduced-motion` is already respected in `styles.css`.

---

## 4. A — The detection screen

`DETECTION.md` is the most differentiating artifact in the repository and exists only as a file at
the root. A tool that ships its own negative results is worth showing.

**Prerequisite:** `drill.py simulate --write` renders markdown from in-memory results and keeps
nothing structured. Persist the sweep as JSON beside the markdown, and serve it. Do not recompute a
sweep on request — the full run takes about twelve minutes.

Show per diagnostic: detection rate against false-positive rate, both with their Wilson intervals;
the sample-size curve; and the "trustworthy from N answers" figure. **The two failures lead.** The
asymmetry claim that does not reproduce, and `needs_rewrite()` flagging 284 of 346 questions on a
learner with nothing wrong, are the most interesting things on the page. If the screen reads as
reassuring, it is wrong.

Cross-link it: where the Rules screen asserts the decision-rule axis, link to the evidence for that
axis, including the part that failed.

---

## 5. E — Next session

One screen answering "what should I do in the next thirty minutes", assembled from what already
exists: weakest rules, the due queue, the dangerous quadrant, coverage projection, and the empty
difficulty bands.

**Every recommendation carries its evidence and its uncertainty.** "Drill `evidence-quality` — 5 of
14 correct, 95% CI 14–61%, and it spans four domains" is a recommendation. "Recommended for you" is
not, and is the failure mode this screen exists to avoid. If a recommendation cannot state why in
one line with numbers, it should not appear.

Nothing here may present a prediction, a readiness score, or a countdown that implies one — see
`CLAUDE.md` §3.7 and the coverage-projection wording already used in `calibration.py`.

---

## 6. C — Exam post-mortem

`cost` — accuracy gap × exam weight — is described in `FRONTEND-BRIEF.md` §4 as the most actionable
number in the app, and it currently renders as a list of rows.

Make it a waterfall: total marks available, then what each domain cost, ordered by damage. Add
time-against-correctness from `seconds_per_question`, which is already stored and never shown — the
interesting quadrant is *fast and wrong*, and it pairs naturally with the confidence data.

Keep the scaled-score caveat exactly as it is.

---

## 7. D — Command palette

⌘K / Ctrl-K. Jump to any screen, start any drill configuration, open any case, run validate. The app
is already keyboard-first; this makes it feel like an instrument rather than a website.

Pure front end, no API. Smallest piece here — do it last, or whenever the other work stalls.

---

## 8. Non-negotiable

1. **No gamification.** `CLAUDE.md` §4. No streaks, XP, badges, confetti, leaderboards, levels,
   celebratory animation. This is the rule most at risk from this brief's own framing.
2. **Every statistic carries its uncertainty**, gated on sample size, on every new surface.
   `CLAUDE.md` §3.6. A number with no interval does not go on a screen.
3. **No answer key, and no case graph, before the learner commits.** §3.12 and `CASES-BRIEF.md`
   §4.1. Add tests, do not assume.
4. **Never a prediction.** No readiness score, no "you will pass", no relabelled scaled score.
5. **Offline.** No CDN, no web fonts, no telemetry. Everything bundled. This has held from the
   start and is easy to break by habit.
6. **`drillkit/`, `drill.py`, `serve.py` stay standard-library only.**
7. **Do not weaken an existing test to make a new screen convenient.**

---

## 9. Done

- B: the graph renders for all three cases, shows the untaken branches, marks the taint edge, is
  keyboard reachable, and is absent from every pre-debrief payload — with a test for that last part
- A: the detection screen reads from persisted results, leads with the failures, and links from the
  Rules screen
- E: every recommendation states its evidence and interval; nothing implies a prediction
- C: the waterfall and the time-against-correctness view, caveat intact
- D: the palette opens on ⌘K and can start a drill
- `python run_tests.py` green, `python drill.py validate` clean, `npm run build` output committed
- `cisa/results/` untouched — use a throwaway profile

---

## 10. How to work

- **Ship B on its own** and look at it before starting A. It is the piece most likely to change
  shape once it is real.
- **Argue with §3.** The layout approach is asserted from three small graphs; if a fourth case
  arrives with a different shape, the design may need to change and that is worth saying.
- The empty and thin cases matter here as much as they did for difficulty: a case never played has
  no path to light up, and the detection screen before a sweep has been run has nothing to show.
- **Ask before**: adding a front-end dependency, touching `drillkit/cases.py`, or altering anything
  in `CLAUDE.md` §3.
