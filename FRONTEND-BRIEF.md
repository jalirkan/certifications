# Front end rebuild — brief for a coding agent

You are rebuilding the browser front end of an offline CISA exam-prep system. The Python engine,
data and HTTP API already exist, are tested (187 tests passing), and **must not be modified**. Your
job is the front end only.

Read this whole file before writing code. Most of it is context you cannot infer from the codebase,
and several of the rules below are ones a reasonable agent would otherwise violate.

---

## 1. What already exists

```
certifications/
  drill.py            CLI front end (works; leave alone)
  serve.py            stdlib HTTP server + JSON API (leave alone)
  drillkit/           the engine: loader, scheduler, exam, games, item analysis, principles
  tests/              187 tests. `python run_tests.py` must stay green.
  web/                the CURRENT front end — vanilla JS. This is what you are replacing.
  cisa/
    outline.json          ISACA exam content outline, all 5 domains
    questions/            292 original questions as JSON
    principles.json       22 transferable decision rules, mapped to questions
    confusable-pairs.json 29 documented concept confusions
    results/              answer logs (personal data — never commit, never delete)
```

Run `python serve.py` to see the current app. It works. It is the reference for behaviour, and the
bar for quality — the rebuild should be better, not merely different.

**A git tag `stdlib-only` marks the pre-rebuild state.** If the rebuild goes badly,
`git checkout stdlib-only` restores a fully working app.

---

## 2. Why the rebuild

The old front end was hand-rolled vanilla JS under a self-imposed "no dependencies" rule. That rule
has been dropped for the front end specifically. It was costing real capability — confidence
intervals are currently drawn with hand-positioned CSS pseudo-elements, and richer visualisation
was impractical.

**The rule still holds for `drillkit/`, `drill.py` and `serve.py`.** Not as dogma: that code is
finished, tested and dependency-free, so adding dependencies there is pure risk with no new
capability. The principle is *put your dependencies where rewrites are cheap.* Front ends get
rewritten; engines do not.

---

## 3. Stack

- **Vite + React + TypeScript**
- A charting library of your choice (Recharts, visx, or similar) — the visualisations below are the
  main reason this rebuild exists
- Build output must be **static files servable by the existing Python server**
- **No runtime CDN calls.** The whole system must work with the network cable unplugged. Bundle
  everything. This constraint is non-negotiable and is the one most likely to be violated by habit.

Suggested layout: source in `frontend/`, build output to `web/` so `serve.py` keeps serving it with
no Python change. Confirm `python serve.py` serves the built bundle before you call it done.

---

## 4. The API contract

Base: same origin. Auth: none. Profile is selected by an **`X-Profile` header** (empty string = the
shared default profile). Every response is JSON; errors are `{ "error": "message" }` with a 4xx/5xx
status.

### `GET /api/bootstrap`
Static-ish reference data. Call once on load.
```
cert, profile, profiles[], questions,
domains[]    { id, name, weight, questions, topics[] { section, topic } }
exam         { questions, minutes, score_scale[2], passing_score, format, verified_on }
principles[] { id, name, statement, why, misapplication, scope, questions }
pairs[]      { id, label, domain, terms[], discriminator, trap, questions }
```

### `GET /api/overview`
Everything the dashboard needs.
```
attempts, correct, accuracy, coverage_seen, coverage_total, study_days,
last7, last7_attempts, weighted_accuracy, games,
domains[] { id, name, weight, accuracy, attempts, low, high, questions }
rules[]   { id, name, accuracy, attempts, low, high, misapplication, scope, seen, total }
topics[]  { label, accuracy, attempts, correct, low, high }
exams[]   { id, created, submitted, answered, total, elapsed, duration }
```
`low`/`high` are **Wilson confidence interval bounds**. See §5 — they are not decoration.
`accuracy` is `null` when there is no data. Handle that everywhere.

### `POST /api/drill/start`
```
→ { mode, n, domain?, section?, topic?, principle?, seed? }
   mode ∈ smart | due | weakest | random | principle | costumes
← { session, mode, header, questions[] }
```

### Question object (the only shape the browser ever sees pre-answer)
```
{ id, domain, section, topic, tag, difficulty, stem,
  options { A, B, C, D }, position, total }
```
**No answer key. No explanations.** This is deliberate — see §5.

### `POST /api/drill/answer`
```
→ { question_id, chosen, session, mode, seconds }
← { id, answer, chosen, correct, why_correct,
    why_wrong { <the three non-answer letters> },
    principle { id, name, statement, misapplication, scope } | null }
```

### `POST /api/game/start`
```
→ { game: "coldread" | "autopsy", n }
← { session, game, ask_types[] { id, label, gloss }, questions[] }
```
- **coldread**: `options` is `{}` — the options are withheld until the user commits to a read.
- **autopsy**: each question also has `answer`, `distractors[]`, and
  `explanations[] { label: "X"|"Y"|"Z", text }` in scrambled order. The label→option mapping is
  held server-side; you cannot compute the answer client-side.

### `POST /api/game/answer`
```
coldread → { game, question_id, session, read, self_report?, seconds }
         ← { expected, read, read_correct, answer, options{}, why_correct, why_wrong{}, principle }
autopsy  → { game, question_id, session, mapping { A:"X", C:"Y", D:"Z" }, seconds }
         ← { correct, matched, total, truth { option: label }, why_correct, principle }
```

### `GET /api/games/stats`
```
total, by_game[] { game, n, ok, secs, accuracy },
misreads[] { expected, read, count },  self_report { y, c, n }
```

### Exams
```
POST /api/exam/new     → { n, minutes, domain? }        ← same shape as GET /api/exam/{id}
GET  /api/exam/{id}    ← { id, submitted, duration, elapsed, remaining, position,
                           answers{}, flagged[], blueprint{}, shortfall{}, questions[] }
POST /api/exam/update  → { id, action, ... }
       action="answer"   { question_id, chosen, seconds }   chosen:"" clears it
       action="flag"     { question_id }                     toggles
       action="position" { position }
       action="tick"     { elapsed }                         clock only moves forward
POST /api/exam/submit  → { id, elapsed }                 ← exam result
GET  /api/exam/{id}/result
GET  /api/exams        ← { exams[] }
```
Exam result:
```
id, total, correct, unanswered, raw, scaled, passed, elapsed, duration, pass_mark,
by_domain[] { domain, name, weight, asked, correct, accuracy, cost },
slowest[] { id, topic, seconds },  guessed_right[] { id, topic },
missed[]  { ...full question, answer, chosen, why_correct, why_wrong{}, principle }
```
`cost` is accuracy-gap × exam-weight. It is the most actionable number in the whole app.

### `GET /api/items?min=5` and `GET /api/card`
Item analysis (question quality) and the generated decision-rules study sheet (`{ text }`).

---

## 5. Non-negotiable rules

These are project conventions. Breaking them silently makes the tool dishonest, which defeats its
purpose. They will not be obvious from the code.

1. **Never present the estimated scaled score as a prediction.** ISACA's scaling is undisclosed and
   the raw threshold moves between exam forms. Wherever `scaled` appears, the caveat appears with
   it. Do not label it "predicted score", "projected score", or "readiness".

2. **Every statistic carries its uncertainty.** `low`/`high` are Wilson bounds and must be rendered
   — as error bars, bands, or explicit ranges. A topic at 2/2 is *not* 100%; it is 34–100%. Small
   samples must visibly read as "unknown", never as a confident number.

3. **Answer keys must never reach the client before the user commits.** Do not cache, prefetch or
   reconstruct them. A user opening devtools mid-exam must learn nothing. There is a test asserting
   the API side; do not undermine it in the client.

4. **No gamification.** No streaks, XP, badges, confetti, leaderboards or levels. These measure
   engagement, not learning, and the user explicitly rejected them. Progress is shown as accuracy
   with intervals, and nothing else.

5. **Short-form game results stay separate from drill and exam accuracy.** They are logged to a
   different file server-side. Never blend them into a single headline number.

6. **Offline, always.** No fonts, scripts, styles or telemetry fetched at runtime.

7. **Results are personal data.** Never commit `cisa/results/**`. Never clear it to tidy up — use a
   throwaway `X-Profile` value when testing.

---

## 6. Screens

Match or beat the current app. Behaviour reference: run `python serve.py`.

1. **Dashboard** — headline stats; accuracy by domain **with confidence intervals** and exam weight;
   weakest decision rules; weakest topics; recent exams; quick-start actions.
2. **Drill** — mode and filter selection, then the runner. **Keyboard-first**: `A`–`D` or `1`–`4` to
   answer, `Enter` to advance, `Esc` to exit. On answering, **each explanation attaches to the
   option it explains** — this is the single most important interaction in the app and the main
   thing the terminal cannot do. The governing decision rule appears below, with its trap.
3. **Mock exam** — countdown timer, flag-for-review, **question palette** (grid showing
   answered / flagged / current, click to jump), save-and-resume with the clock stopped,
   auto-submit at zero. Result screen with per-domain breakdown, the weighted `cost` ranking, and
   full review of missed questions.
4. **Short form** — Cold Read (options genuinely hidden until the read is committed) and Autopsy
   (match scrambled explanations to their options). Plus the **misread table**: which question type
   was mistaken for which.
5. **Decision rules** — diagnostic ranked weakest-first; for weak rules show the misapplication and
   scope; one click to drill that rule across every domain. Plus the generated study card.
6. **Question bank** — item analysis (flags questions that are *badly written*, not user weakness)
   and the confusable-pair reference.

Profile switcher in the chrome, persisted to localStorage, sent as `X-Profile`.

---

## 7. Where a real charting library should earn its place

The old UI could not do these. They are the reason for the rebuild:

- **Domain accuracy with error bars**, x-axis weighted by exam share, so visual area maps to marks
  available rather than to topic count.
- **Decision-rule diagnostic** as a ranked dot-plot with interval whiskers — 22 rules is too many
  for stacked bars.
- **Accuracy over time**, per domain, from the timestamped attempt log.
- **Cold Read misread matrix** as a small heatmap or Sankey (question type → how it was read).
- **Difficulty distribution** of the bank from item analysis.

Keep them quiet and readable. Dark UI, restrained palette, no decorative animation.

---

## 8. Definition of done

- `npm run build` produces static files that `python serve.py` serves with no Python change
- `python run_tests.py` still passes 187 tests (you should not have touched anything it covers)
- Every screen in §6 works against the real API with real data
- All seven rules in §5 hold — check each one explicitly before declaring done
- Works with the network disconnected after build
- Keyboard flow works end to end without a mouse
- No `cisa/results/**` committed

Ask before: modifying anything in `drillkit/`, `drill.py`, `serve.py`, or the JSON data files.
