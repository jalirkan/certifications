# Front end

Browser front end for the CISA study system. Vite + React + TypeScript, with Recharts for the
visualisations.

## Build

```bash
npm install        # once
npm run build      # typechecks, then emits to ../web
```

`serve.py` serves `../web` unchanged, so after a build the normal workflow is just:

```bash
python serve.py
```

**`../web` is build output.** Every build wipes it. Do not hand-edit anything in there — edit
`src/` and rebuild. The pre-rebuild vanilla-JS front end is preserved at the git tag `stdlib-only`.

## Development

```bash
python serve.py --no-browser     # terminal 1: the real engine on :8765
npm run dev                      # terminal 2: hot reload on :5173, /api proxied to 8765
```

The dev server proxies `/api` to the Python server, so the dev loop runs against the real question
bank and your real results — use a throwaway profile in the switcher rather than the shared one.

## Constraints that are not negotiable

These come from `../CLAUDE.md` and `../FRONTEND-BRIEF.md`. They are easy to break by habit:

- **No runtime network access.** No CDN, no web fonts, no telemetry. Everything is bundled and the
  favicon is a data URI. The whole system has to work with the cable unplugged.
- **No answer key reaches the browser before the user commits.** `Question` in `src/api/types.ts`
  has no answer field, and nothing caches or prefetches a revealed payload.
- **Every statistic carries its uncertainty.** `low`/`high` are Wilson bounds and must be rendered.
  Below `MIN_CLAIM` attempts, `claim()` in `src/lib/format.ts` prints the range instead of a point
  estimate, so a small sample reads as unknown rather than as a confident number.
- **The scaled exam score is never a prediction.** The caveat travels with the number.
- **Short-form game results never mix into drill or exam accuracy.**
- **No gamification.** No streaks, XP, badges, confetti, leaderboards.

## Layout

```
src/
  api/         typed client and the API contract as TypeScript
  app/         provider (bootstrap, profile, toasts) and the nav rail
  charts/      the five visualisations + shared chart tokens
  lib/         formatting (including the interval helpers) and hooks
  screens/     one file per screen
  ui/          design-system primitives and the shared question view
```

Charts are split deliberately: Recharts handles the rule dot plot, the time series and the
difficulty bars, where its axes, tooltips and `ErrorBar` earn their keep. The domain Marimekko and
the misread matrix are hand-built SVG, because variable-width bars and a labelled sparse matrix are
things a generic chart library makes harder rather than easier.
