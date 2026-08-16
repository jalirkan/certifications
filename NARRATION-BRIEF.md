# Case narration — handoff brief

> **Status: built 2026-08-01.** `frontend/src/lib/speech.ts`, `frontend/src/ui/Narration.tsx`,
> wired into `Cases.tsx`, with `tests/test_narration.py` (16 structural guards) and the §6
> asymmetry note in the README. Every item in §7 is on disk.
>
> §1's feasibility finding held, with one correction. It says to listen for `voiceschanged` before
> populating a picker. On the browser this was tested in, `voiceschanged` **never fires** — voices
> were empty at first call and present at 850ms. A pure listener waits forever there; a fixed
> timeout was the first fix and was also wrong, because 850ms on one machine is not 850ms on a
> slower one and the failure is silent (the feature reports "no voice installed" and disables
> itself). `whenVoicesReady()` now listens *and* polls to a 6s deadline, resolving the moment
> voices appear either way.
>
> §3 was implemented as written and is enforced by the type system rather than by convention:
> `speak()` takes a branded `Narratable` that only the `narrate` allow-list can mint, so passing
> `option.text` is a compile error. Four deliberate mutations of that mechanism were each caught by
> the test suite.
>
> **One thing §8 asks for that was not done:** whether listening actually feels better than reading
> is a judgment about audio, and the agent that built this could not hear it. The mechanism is
> verified end to end — a full tainted d5 path played with narration on, 16 utterances, no option
> text among them — but the comfort question is open and belongs to whoever uses it.
>
> **§4.3 was relaxed on purpose, by the project owner, after the button-only version shipped.**
> There is now an opt-in "read each passage automatically", off by default. The part of the rule
> that mattered is kept exactly — nothing speaks at a screen you merely arrived at — because
> auto-reading arms only after you act *inside* a run: choosing an option or pressing Continue.
> Opening a case, resuming one and loading the debrief are all silent, verified by sitting on a
> freshly opened case for three seconds with the setting on and counting zero utterances.
>
> That change also produced the sharpest bug in this feature, and it is worth recording because it
> was **invisible on screen**. `useNarration` returns a fresh handle object every render, so an
> effect depending on the handle re-fires every render — and `say()` flips `speaking` and notifies
> subscribers, which *causes* a render. The screen looked perfect: right text, right order. The
> synthesiser was called **24,664 times for one decision**. It surfaced only from counting calls
> rather than watching the page. Fixed with primitive dependencies plus a per-passage guard, and
> `tests/test_narration.py` now fails if any effect in the case screen depends on the bare handle.

> **Extended to drills 2026-08-01, at the owner's request.** §3 anticipated this exactly — "the
> same applies to the question bank if narration is extended there later: stem yes, options no" —
> and that is what shipped. The stem gets a button; the four options never do. The explanations are
> read as one passage that names options by letter, which is safe for a structural reason rather
> than a careful one: the function takes a `Reveal`, and a Reveal physically does not carry option
> text (see `webapi.reveal`), so there is nothing there to leak. Drills are button-only — auto-read
> is a case behaviour and the toggle is hidden on the drill screen rather than shown doing nothing.
>
> Playing it surfaced a bug that reading the code would not have: `speaking` is narrator-wide, so
> with two speak buttons on one screen *both* flipped to "Stop" together, the stem offering to stop
> the explanations it was not reading. Invisible with one button per screen, obvious with two.

For a coding agent with a terminal. Read `CLAUDE.md` first, then `cisa/cases/SCHEMA.md`.

Independent of `DIFFICULTY-BRIEF.md`; either can ship first.

---

## 1. Feasibility, since that was the question

**High, and it costs nothing.** The browser has a speech synthesiser built in — `window.speechSynthesis`
with `SpeechSynthesisUtterance`, part of the Web Speech API. Supported in Chrome, Edge, Firefox,
Safari, Opera and Samsung Internet. No library, no service, no key, no cost.

**It satisfies the offline rule.** Synthesis runs against the operating system's local voices with no
network. Some browsers additionally expose cloud voices, and the API marks them: every voice carries
`localService`, so filtering to `localService === true` guarantees the utterance text never leaves the
machine. That filter is not optional here — see §4.

So the whole feature lives in `frontend/`, which is exactly where dependencies are cheap under the
rule in the workstation `CLAUDE.md`. The Python side does not change at all.

---

## 2. Why cases specifically

A case is prose. An opening that sets a scene, a situation that moves, a consequence narrated back
after each decision. That is material a person can absorb by listening, and hearing an engagement
described rather than reading it makes the format feel like the thing it is imitating.

There is also a plain accessibility argument, and a screen-fatigue one for a tool someone will use
for months.

**What this is not:** a claim that narration improves exam performance. The exam is read, silently,
under time pressure. Nothing here trains that better than reading does, and the harness in
`SIMULATION-BRIEF.md` cannot measure it either. Ship it as comfort and access, and do not let any
copy in the interface imply a learning benefit that has not been established.

---

## 3. The design call that matters

**Narrate the narrative. Never narrate the options.**

Opening, situation and consequence are prose, consumed in order, and they suit audio.

The four options are a **comparison task**. You hold them side by side, re-read the second against
the fourth, notice that two differ by one word. Read aloud in sequence they arrive one at a time and
leave, which converts a reading task into a working-memory task and makes the decision harder for a
reason that has nothing to do with audit judgment.

The same applies to the question bank if narration is extended there later: stem yes, options no.

If you build it and disagree after using it, say so — but the default is that the options stay on
the page and only the page.

---

## 4. Non-negotiable

1. **Local voices only.** Filter on `localService`. A cloud voice would send case text to a vendor's
   servers, which breaks the offline promise the whole project is built on and does it invisibly.
   If no local voice is available, disable the feature and say why rather than falling back.
2. **Never speak the options.** §3.
3. **No autoplay.** Narration starts when the learner asks for it. A case that begins talking on its
   own is hostile, and browsers block it without a user gesture anyway.
4. **Front end only.** Do not add a speech dependency to `drillkit/`, `drill.py` or `serve.py`.
   Those stay standard-library only, and the CLI gets nothing here — see §6.
5. **No claim of learning benefit** in any interface copy.

---

## 5. Implementation notes worth having in advance

These are the known rough edges of `speechSynthesis`, and each one produces a confusing bug if you
meet it cold:

- **Voices load asynchronously.** `getVoices()` is frequently empty on first call; listen for
  `voiceschanged` before populating a picker.
- **Chrome truncates long utterances**, historically around fifteen seconds. Chunk by sentence and
  queue the chunks rather than passing a whole paragraph.
- **`pause()` / `resume()` are unreliable across browsers.** Prefer stop-and-restart-from-the-top of
  the current chunk over a real pause.
- **Cancel on navigation.** Moving to the next node while the previous consequence is still being
  spoken is the obvious bug; `speechSynthesis.cancel()` on unmount and on any node change.
- Persist voice, rate and on/off in `localStorage`. Rate matters more than voice — most people want
  it faster than the default once they are used to it.

---

## 6. The asymmetry, stated deliberately

Every other feature in this project works from both `drill.py` and the browser. This one will not,
because the browser ships a speech engine and the terminal does not, and closing the gap would mean
a Python TTS dependency in exactly the layer that is deliberately dependency-free.

That is an acceptable trade and it should be **written down in the README** rather than left for
someone to notice. If a terminal equivalent is ever wanted, the honest option is a separate opt-in
script outside `drillkit/`, not a dependency inside it.

---

## 7. Done

- Case opening, situation and consequence can be narrated on request, in the browser
- Options are never spoken, and there is a test or a clear code-level guarantee of that
- Only `localService` voices are offered; the feature disables itself with an explanation if none exist
- Voice, rate and enabled state persist across sessions
- Speech stops on navigation and on unmount
- No autoplay anywhere
- The CLI asymmetry is documented in the README
- `python run_tests.py` green, `python drill.py validate` clean, `npm run build` output committed

---

## 8. How to work

- **Play a whole case with narration on before calling it done**, including at least one path that
  fires a taint. If listening to the consequence and reading the options does not feel better than
  reading both, say so — this is a comfort feature and comfort is the whole test.
- **Argue with §3 from experience**, not from theory, if you come to disagree with it.
- **Ask before**: touching `cisa/cases/*.json`, `drillkit/cases.py`, or anything in `CLAUDE.md` §3.
