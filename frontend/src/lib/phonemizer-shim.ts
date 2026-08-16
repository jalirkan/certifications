/**
 * Load `phonemizer` at runtime instead of letting the bundler touch it.
 *
 * kokoro-js imports `phonemizer` internally to turn text into phonemes. That
 * package embeds espeak-ng as an Emscripten module with its language data as a
 * base64 blob, and **Vite's minifier breaks it**: bundled, espeak initialises
 * with an empty language table and every call dies with
 *
 *     Invalid language identifier: "en-us". Should be one of: .
 *
 * — an empty list where the languages should be. Served unbundled and imported
 * at runtime, the identical file works first time. That was the diagnosis:
 * same version, same browser, only the bundling differs.
 *
 * So `vite.config.ts` aliases `phonemizer` to this file, and this file pulls
 * the untouched copy from `/models/runtime/`, which `get_voices.py` puts there
 * beside the ONNX runtime. Still local, still no network — the file comes off
 * the same disk as everything else.
 *
 * The `@vite-ignore` is essential: without it the bundler would follow this
 * import and re-introduce the exact problem it exists to avoid.
 */

const URL_PATH = '/models/runtime/phonemizer.js'

type PhonemizeFn = (text: string, lang?: string) => Promise<string[]>

let real: Promise<{ phonemize: PhonemizeFn }> | null = null

function load(): Promise<{ phonemize: PhonemizeFn }> {
  if (!real) {
    real = import(/* @vite-ignore */ URL_PATH) as Promise<{ phonemize: PhonemizeFn }>
  }
  return real
}

export async function phonemize(text: string, lang?: string): Promise<string[]> {
  const mod = await load()
  return mod.phonemize(text, lang)
}
