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
  | { type: 'backend'; name: string }
  | { id: number; type: 'loaded' }
  | { id: number; type: 'audio'; wav: ArrayBuffer }
  | { id: number; type: 'error'; message: string }

let tts: KokoroTTS | null = null
let loading: Promise<KokoroTTS> | null = null
/** Which backend actually won, for the UI to report honestly. */
let backend = ''

/**
 * Pick a backend, preferring the GPU but never depending on it.
 *
 * Two things have to line up for WebGPU, not one: an adapter, and a model
 * quantization the WebGPU execution provider will actually run. q8 is what
 * `get_voices.py` fetches by default because it is smallest and best on CPU,
 * and the WebGPU provider does not reliably support its quantized operators -
 * so if `model_fp16.onnx` is present (via `get_voices.py --webgpu`) that is
 * what the GPU path uses.
 *
 * Every candidate is *tried*, in order, and a failure falls through to the
 * next. That matters more than the ordering: an adapter reporting itself as
 * available is not a promise that a session will build on it.
 */
async function candidates(): Promise<Array<{ device: 'webgpu' | 'wasm'; dtype: 'fp16' | 'q8' }>> {
  const out: Array<{ device: 'webgpu' | 'wasm'; dtype: 'fp16' | 'q8' }> = []
  const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown> } }).gpu
  if (gpu) {
    let adapter: unknown = null
    try {
      adapter = await gpu.requestAdapter()
    } catch {
      adapter = null
    }
    if (adapter) {
      const fp16 = await fetch(`${MODEL_ROOT}${MODEL_ID}/onnx/model_fp16.onnx`,
                               { method: 'HEAD' }).then((r) => r.ok).catch(() => false)
      if (fp16) out.push({ device: 'webgpu', dtype: 'fp16' })
      out.push({ device: 'webgpu', dtype: 'q8' })
    }
  }
  out.push({ device: 'wasm', dtype: 'q8' })   // always last, always works
  return out
}

const post = (msg: FromWorker, transfer?: Transferable[]) =>
  (self as unknown as Worker).postMessage(msg, transfer ?? [])

async function ensure(): Promise<KokoroTTS> {
  if (tts) return tts
  if (!loading) {
    loading = (async () => {
      const tried: string[] = []
      for (const option of await candidates()) {
        const tag = `${option.device}/${option.dtype}`
        try {
          const model = await KokoroTTS.from_pretrained(MODEL_ID, {
            dtype: option.dtype,
            device: option.device,
            progress_callback: (info: { status?: string; progress?: number }) => {
              if (info?.status === 'progress' && typeof info.progress === 'number') {
                post({ type: 'progress', fraction: info.progress / 100 })
              }
            },
          })
          tts = model
          backend = tag
          post({ type: 'backend', name: tag })
          return model
        } catch (err) {
          tried.push(`${tag}: ${err instanceof Error ? err.message : String(err)}`)
        }
      }
      throw new Error(`No usable backend. Tried ${tried.join(' | ')}`)
    })()
  }
  return loading
}

self.onmessage = async (ev: MessageEvent<ToWorker>) => {
  const msg = ev.data
  try {
    if (msg.type === 'load') {
      await ensure()
      post({ type: 'backend', name: backend })
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
