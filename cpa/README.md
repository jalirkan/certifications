# CPA prep — lives in per-section certs

CPA is four separate exams (AUD, FAR, REG cores plus one chosen discipline),
each with its own blueprint, format, timing and score scale. One cert = one
exam is the model the engine's blueprint sampling, mock timing and scaled-score
honesty all assume, so each section gets its own cert folder rather than one
`cpa/` umbrella.

Active now:

- **`cpa-aud/`** — Auditing and Attestation (AUD Core). Verified January-2026
  blueprint outline, 60 original questions, every item adversarially reviewed.
  `python drill.py --cert cpa-aud drill -n 20`, or switch certs from the rail
  in the web app.

When FAR, REG or a discipline starts: follow the `cpa-aud/` pattern (verify the
current blueprint online first — see CLAUDE.md §3 rule 2). The engine needs no
code changes.

Task-based simulations remain unmodeled, and every AUD exam surface says so.
Keep it that way until simulations get a real design rather than a bolt-on.
