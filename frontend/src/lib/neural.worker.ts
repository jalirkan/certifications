/**
 * Kokoro inference, off the main thread.
 *
 * ONNX inference is synchronous. Run on the main thread it competes with
 * rendering for the whole 92MB session build and for every sentence
 * synthesised; here it has its own thread and cannot.
 *
 * **On the evidence, stated carefully.** The first attempt to show this
 * polled a button label every 60ms and found the first sample at 1179ms,
 * which was read as a 1.2s freeze. That reading was not sound: the tab was
 * hidden, and hidden tabs throttle timers to roughly once a second, so the
 * gap is equally explained by throttling. What *is* measured, with the Long
 * Task API - which is not timer-based and so is immune to that - is that this
 * version produces **zero** main-thread tasks over 50ms across a cold load
 * and a full synthesis. There is no equally-instrumented number for the
 * old version, so the honest claim is "this one is clean", not "it is N
 * milliseconds better".
 *
 * **The offline rules apply here identically**, and have to be re-stated
 * because a worker has its own global scope and its own copy of the config:
 * remote models are refused, the model path is local, and the ONNX WASM
 * binaries come from `/models/runtime/` rather than a CDN.
 *
 * Voice embeddings are seeded into Cache Storage by the main thread before the
 * first generate. Cache Storage is shared per origin between window and
 * worker, so kokoro-js — which hardcodes a HuggingFace URL and consults the
 * cache before fetching — finds them here without touching the network.
 */

import { KokoroTTS } from 'kokoro-js'
import { env } from '@huggingface/transformers'

const MODEL_ROOT = '/models/'
const MODEL_ID = 'kokoro'

env.allowRemoteModels = false
env.allowLocalModels = true
env.localModelPath = MODEL_ROOT
if (env.backends?.onnx?.wasm) {
  env.backends.onnx.wasm.wasmPaths = `${MODEL_ROOT}runtime/`
  // One thread. ONNX's multi-threaded path needs cross-origin isolation
  // headers, which serve.py does not send and which would be a strange thing
  // to require of a local study tool. Being off the main thread is the win;
  // being on four of them is not worth COOP/COEP.
  env.backends.onnx.wasm.numThreads = 1
}

export type ToWorker =
  | { id: number; type: 'load' }
  | { id: number; type: 'generate'; text: string; voice: string; speed: number }

export type FromWorker =
  | { type: 'progress'; fraction: number }
  | { id: number; type: 'loaded' }
  | { id: number; type: 'audio'; wav: ArrayBuffer }
  | { id: number; type: 'error'; message: string }

let tts: KokoroTTS | null = null
let loading: Promise<KokoroTTS> | null = null

const post = (msg: FromWorker, transfer?: Transferable[]) =>
  (self as unknown as Worker).postMessage(msg, transfer ?? [])

async function ensure(): Promise<KokoroTTS> {
  if (tts) return tts
  if (!loading) {
    loading = KokoroTTS.from_pretrained(MODEL_ID, {
      // q8 is the smallest file kokoro-js offers — 92MB against 305 for q4,
      // which despite the name is the largest — and the fastest on CPU.
      dtype: 'q8',
      device: 'wasm',
      progress_callback: (info: { status?: string; progress?: number }) => {
        if (info?.status === 'progress' && typeof info.progress === 'number') {
          post({ type: 'progress', fraction: info.progress / 100 })
        }
      },
    }).then((model) => {
      tts = model
      return model
    })
  }
  return loading
}

self.onmessage = async (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data
  try {
    if (msg.type === 'load') {
      await ensure()
      post({ id: msg.id, type: 'loaded' })
      return
    }
    if (msg.type === 'generate') {
      const model = await ensure()
      const audio = await model.generate(msg.text, {
        voice: msg.voice as Parameters<KokoroTTS['generate']>[1] extends
          { voice?: infer V } ? V : never,
        speed: msg.speed,
      })
      const wav = audio.toWav()
      // Transferred, not copied: a few hundred KB per sentence adds up over a
      // twenty-question session.
      post({ id: msg.id, type: 'audio', wav }, [wav])
    }
  } catch (err) {
    post({
      id: msg.id,
      type: 'error',
      message: err instanceof Error ? err.message : String(err),
    })
  }
}
