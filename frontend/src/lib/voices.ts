/**
 * The neural voice list, as data.
 *
 * Deliberately its own file with no imports: the settings UI needs these names
 * before any engine is loaded, and importing them from `neural.ts` would pull
 * transformers.js and the ONNX bindings — about 2MB — into the main bundle for
 * everyone, including people who never turn narration on.
 *
 * Grades are Kokoro's own published quality marks; these are the A and B ones.
 */
export const NEURAL_VOICES: { id: string; label: string }[] = [
  { id: 'af_heart', label: 'Heart — American, female' },
  { id: 'af_bella', label: 'Bella — American, female' },
  { id: 'af_nicole', label: 'Nicole — American, female' },
  { id: 'af_aoede', label: 'Aoede — American, female' },
  { id: 'af_kore', label: 'Kore — American, female' },
  { id: 'af_sarah', label: 'Sarah — American, female' },
  { id: 'am_michael', label: 'Michael — American, male' },
  { id: 'am_fenrir', label: 'Fenrir — American, male' },
  { id: 'am_puck', label: 'Puck — American, male' },
  { id: 'bf_emma', label: 'Emma — British, female' },
  { id: 'bf_isabella', label: 'Isabella — British, female' },
  { id: 'bm_george', label: 'George — British, male' },
  { id: 'bm_fable', label: 'Fable — British, male' },
]
