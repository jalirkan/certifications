/**
 * Neural narration: Kokoro-82M, running on this machine, in this browser.
 *
 * The system voices are 2013-era concatenative synthesis and sound it. This is
 * an 82M-parameter open-weight model that produces something you can listen to
 * for an hour. It costs no key, no account and no per-word fee, and — the part
 * that matters for this project — no network at study time.
 *
 * ## Two things fetch from the internet by default. Both are disabled here.
 *
 * **1. The ONNX runtime's WebAssembly binaries.** `transformers.js` points
 * `wasmPaths` at a CDN out of the box. Left alone, every narration would pull
 * ~11MB from jsdelivr.
 *
 * **2. The voice embeddings — and this one is not configurable.** kokoro-js
 * hardcodes the URL:
 *
 *     const a = `https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX
 *                /resolve/main/voices/${e}.bin`
 *
 * It does not consult `localModelPath`. So the weights would load from disk
 * while every voice was fetched from HuggingFace — an app that looks perfectly
 * offline, works fine on a connected machine, and quietly breaks the promise
 * the whole project rests on. It is the kind of failure that ships.
 *
 * It reads Cache Storage before fetching, though, which is the way in: we put
 * the bytes there ourselves, read from our own server off local disk. Its
 * `fetch` is then never reached. `seedVoice` below does that, and there is a
 * test asserting the URL constant still matches the one in the library — if a
 * kokoro-js upgrade changes it, the seed would silently stop matching and the
 * fetch would come back.
 *
 * ## Why it is not the default
 *
 * ~103MB of weights that `get_voices.py` has to fetch first, and CPU synthesis
 * is not instant. The system voices stay the default and the fallback; this is
 * opt-in, and when the model is absent the UI says so rather than pretending.
 */

import { KokoroTTS } from 'kokoro-js'
import { env } from '@huggingface/transformers'

/** Where get_voices.py puts things, and serve.py serves them from. */
const MODEL_ROOT = '/models/'
const MODEL_ID = 'kokoro'
const VOICE_DIR = `${MODEL_ROOT}${MODEL_ID}/voices/`

/**
 * Mirrors the constant inside kokoro-js. Must match byte for byte or the cache
 * seed misses and the library falls back to fetching. Asserted by a test.
 */
const HF_VOICES = 'https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/voices/'
const VOICE_CACHE = 'kokoro-voices'

/** The list lives in ./voices so the settings UI can read it without pulling
 *  this module - and transformers.js with it - into the main bundle. */
export { NEURAL_VOICES } from './voices'

let configured = false

/** Point every loader at local disk, once, before anything loads. */
function configure(): void {
  if (configured) return
  configured = true
  env.allowRemoteModels = false        // refuse the Hub outright
  env.allowLocalModels = true
  env.localModelPath = MODEL_ROOT
  // Otherwise this is a jsdelivr URL and narration pulls ~11MB per cold start.
  if (env.backends?.onnx?.wasm) {
    env.backends.onnx.wasm.wasmPaths = `${MODEL_ROOT}runtime/`
  }
}

/** Is the model on disk? Cheap HEAD-ish probe, used to drive the UI. */
export async function modelPresent(): Promise<boolean> {
  try {
    const res = await fetch(`${MODEL_ROOT}${MODEL_ID}/config.json`,
                            { method: 'GET', cache: 'force-cache' })
    return res.ok
  } catch {
    return false
  }
}

/**
 * Put a voice into the cache kokoro-js reads, sourced from our own server.
 *
 * This is the interception described at the top. Reading the response body
 * from `/models/...` and storing it under the HuggingFace key means the
 * library's `caches.match` hits and its `fetch` never runs.
 */
async function seedVoice(voice: string): Promise<void> {
  const key = `${HF_VOICES}${voice}.bin`
  let cache: Cache
  try {
    cache = await caches.open(VOICE_CACHE)
  } catch {
    return   // no Cache Storage; the library will try to fetch and will fail
  }
  if (await cache.match(key)) return

  const res = await fetch(`${VOICE_DIR}${voice}.bin`)
  if (!res.ok) throw new Error(`Voice ${voice} is not downloaded.`)
  const body = await res.arrayBuffer()
  await cache.put(key, new Response(body))
}

export type NeuralState =
  | { phase: 'absent' }
  | { phase: 'idle' }
  | { phase: 'loading'; progress: number }
  | { phase: 'ready' }
  | { phase: 'error'; message: string }

/**
 * One loaded model, shared across the app.
 *
 * Module-level rather than per-component: the weights are ~92MB in memory once
 * decoded, and a second copy per mounted screen would be a memory bug that
 * looks like a slow app.
 */
let tts: KokoroTTS | null = null
let loading: Promise<KokoroTTS> | null = null

export async function loadModel(
  onProgress?: (fraction: number) => void,
): Promise<KokoroTTS> {
  if (tts) return tts
  if (loading) return loading

  configure()
  loading = KokoroTTS.from_pretrained(MODEL_ID, {
    // q8 is both the smallest file kokoro-js offers (92MB against 305 for q4,
    // which despite the name is the largest) and the fastest on CPU.
    dtype: 'q8',
    device: 'wasm',
    progress_callback: (info: { status?: string; progress?: number }) => {
      if (onProgress && info?.status === 'progress' && typeof info.progress === 'number') {
        onProgress(info.progress / 100)
      }
    },
  }).then((model) => {
    tts = model
    loading = null
    return model
  }).catch((err) => {
    loading = null
    throw err
  })
  return loading
}

export function isLoaded(): boolean {
  return tts !== null
}

/** kokoro-js types `voice` as a literal union; settings hold a plain string
 *  validated against NEURAL_VOICES, so one cast at the boundary. */
type GenerateOpts = NonNullable<Parameters<KokoroTTS['generate']>[1]>
type VoiceId = NonNullable<GenerateOpts['voice']>

/**
 * Speak a queue of sentences, playing each as the next is synthesised.
 *
 * Synthesis is not instant on CPU, so waiting for a whole passage before any
 * sound would put several seconds of silence after the button press. Playing
 * piece one while piece two renders hides almost all of it.
 *
 * `token` is compared on every await: cancellation has to survive being called
 * mid-synthesis, which is the common case (you press Continue while it talks).
 */
export class NeuralSpeaker {
  private token = 0
  private audio: HTMLAudioElement | null = null
  private urls: string[] = []

  get speaking(): boolean {
    return this.audio !== null
  }

  async speak(pieces: string[], voice: string, speed: number,
              onDone: () => void): Promise<void> {
    const mine = ++this.token
    const model = tts
    if (!model || !pieces.length) return

    try {
      await seedVoice(voice)
      if (mine !== this.token) return

      const v = voice as VoiceId
      let next = model.generate(pieces[0], { voice: v, speed })
      for (let i = 0; i < pieces.length; i++) {
        const audio = await next
        if (mine !== this.token) return
        // Start the next render before playing this one, so synthesis and
        // playback overlap instead of alternating.
        next = i + 1 < pieces.length
          ? model.generate(pieces[i + 1], { voice: v, speed })
          : Promise.resolve(audio)
        await this.play(audio.toBlob(), mine)
        if (mine !== this.token) return
      }
    } finally {
      if (mine === this.token) {
        this.cleanup()
        onDone()
      }
    }
  }

  private play(blob: Blob, mine: number): Promise<void> {
    return new Promise((resolve) => {
      if (mine !== this.token) return resolve()
      const url = URL.createObjectURL(blob)
      this.urls.push(url)
      const el = new Audio(url)
      this.audio = el
      const finish = () => {
        el.onended = null
        el.onerror = null
        resolve()
      }
      el.onended = finish
      el.onerror = finish
      void el.play().catch(finish)
    })
  }

  stop(): void {
    this.token++
    this.cleanup()
  }

  private cleanup(): void {
    if (this.audio) {
      this.audio.pause()
      this.audio = null
    }
    // Object URLs are not garbage collected on their own; a 20-question
    // session would leak every rendered sentence without this.
    for (const url of this.urls) URL.revokeObjectURL(url)
    this.urls = []
  }
}

/** Exposed for the test that keeps the cache key in step with the library. */
export const _internals = { HF_VOICES, VOICE_CACHE, MODEL_ROOT }
