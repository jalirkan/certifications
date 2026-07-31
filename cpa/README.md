# CPA prep — placeholder

Deliberately empty until CISA is passed. The structure is reserved so the drill engine picks it up
without any code changes when the time comes.

To activate:

1. Verify the **current** AICPA CPA Exam Blueprints online before writing anything — the CPA exam
   changed structure under the CPA Evolution model (three core sections plus one discipline), and
   the blueprints are reissued regularly. Do not write content from memory or from this note.
2. Create `cpa/outline.json` in the same shape as `cisa/outline.json`, using the blueprint's own
   area / group / topic names and weights.
3. Create `cpa/questions/` and `cpa/results/`.
4. Everything then works: `python drill.py --cert cpa drill -n 20`, `python drill.py --cert cpa stats`.

Note that CPA testing includes task-based simulations alongside multiple-choice. This engine handles
multiple choice only; simulations will need either a separate approach or an extension to the
question schema.
