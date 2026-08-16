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
 *
 * ## This file is the client; the model lives in a worker
 *
 * Inference is synchronous and used to run here, freezing the page for the
 * whole session build and every sentence. `neural.worker.ts` now owns the
 * model and this module is the request/response side plus audio playback.
 * Voice-cache seeding stays here because Cache Storage is shared per origin,
 * so seeding from the window is visible to the worker.
 */

import type { FromWorker, ToWorker } from './neural.worker'

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

/**
 * The worker, and the request/response plumbing over it.
 *
 * One worker for the app: the weights are ~92MB once decoded and a second copy
 * per screen would be a memory bug that presents as a slow machine.
 */
let worker: Worker | null = null
let nextId = 1
const pending = new Map<number, {
  resolve: (wav: ArrayBuffer) => void
  reject: (err: Error) => void
}>()
let onProgress: ((fraction: number) => void) | null = null
let loadedFlag = false
let backendName = ''

/** Which backend the worker settled on, e.g. "webgpu/fp16" or "wasm/q8". */
export function backend(): string {
  return backendName
}

function ensureWorker(): Worker {
  if (worker) return worker
  worker = new Worker(new URL('./neural.worker.ts', import.meta.url),
                      { type: 'module' })
  worker.onmessage = (ev: MessageEvent<FromWorker>) => {
    const msg = ev.data
    if (msg.type === 'progress') {
      onProgress?.(msg.fraction)
      return
    }
    if (msg.type === 'backend') {
      backendName = msg.name
      return
    }
    const waiting = pending.get(msg.id)
    if (!waiting) return
    pending.delete(msg.id)
    if (msg.type === 'error') waiting.reject(new Error(msg.message))
    else if (msg.type === 'audio') waiting.resolve(msg.wav)
    else waiting.resolve(new ArrayBuffer(0))   // 'loaded'
  }
  worker.onerror = (ev) => {
    const err = new Error(ev.message || 'The voice worker failed to start.')
    for (const [, waiting] of pending) waiting.reject(err)
    pending.clear()
  }
  return worker
}

/** Distributive, so the union's members keep their own shapes. A plain
 *  `Omit<ToWorker, 'id'>` collapses them and loses `text`. */
type Unidentified<T> = T extends { id: number } ? Omit<T, 'id'> : never

function send(msg: Unidentified<ToWorker>): Promise<ArrayBuffer> {
  const w = ensureWorker()
  const id = nextId++
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    w.postMessage({ ...msg, id } as ToWorker)
  })
}

export function isLoaded(): boolean {
  return loadedFlag
}

/**
 * Build the inference session.
 *
 * Now genuinely asynchronous from the page's point of view: the heavy work is
 * on the worker thread, so `onProgress` callbacks reach React and actually
 * repaint. That was impossible while this ran inline.
 */
export async function loadModel(
  progress?: (fraction: number) => void,
): Promise<void> {
  onProgress = progress ?? null
  try {
    await send({ type: 'load' })
    loadedFlag = true
  } finally {
    onProgress = null
  }
}

/**
 * Speak a queue of sentences, playing each as the next is synthesised.
 *
 * Synthesis is not instant, so waiting for a whole passage before any sound
 * would put several seconds of silence after the button press. Rendering the
 * next sentence while the current one plays hides almost all of it - and with
 * the work on a worker, playback is no longer competing with it for the thread.
 *
 * `token` is compared after every await: cancelling has to survive being
 * called mid-synthesis, which is the common case - you press Continue while it
 * is still talking.
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
    if (!pieces.length) return

    try {
      // Seeded from the window, not the worker: Cache Storage is shared per
      // origin, so this is where kokoro-js finds the voice without fetching.
      await seedVoice(voice)
      if (mine !== this.token) return

      let next = send({ type: 'generate', text: pieces[0], voice, speed })
      for (let i = 0; i < pieces.length; i++) {
        const wav = await next
        if (mine !== this.token) return
        next = i + 1 < pieces.length
          ? send({ type: 'generate', text: pieces[i + 1], voice, speed })
          : Promise.resolve(new ArrayBuffer(0))
        await this.play(new Blob([wav], { type: 'audio/wav' }), mine)
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
