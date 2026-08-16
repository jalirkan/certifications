/**
 * Case narration over the browser's built-in speech synthesiser.
 *
 * No library, no service, no key, no cost — `window.speechSynthesis` is part of
 * the platform. **This is the only file in the app that touches it**, which is
 * what makes the guarantee below checkable rather than a promise (there is a
 * test asserting exactly that).
 *
 * ## The guarantee: options are never spoken
 *
 * Opening, situation and consequence are prose, consumed in order, and they
 * suit audio. The four options are a *comparison task*: you hold them side by
 * side, re-read the second against the fourth, notice two differ by one word.
 * Read aloud they arrive one at a time and leave, which converts a reading task
 * into a working-memory task and makes the decision harder for a reason that
 * has nothing to do with audit judgment.
 *
 * So `speak()` does not accept a string. It accepts `Narratable`, a branded
 * type produced only by `narratable()`, which is called only on prose fields.
 * Passing `option.text` is a compile error, not a code-review catch. If someone
 * later decides options should be spoken, they have to delete this paragraph
 * and defeat the type on purpose — which is the point.
 *
 * ## Local voices only
 *
 * Every voice carries `localService`. A cloud voice would ship case text to a
 * vendor's servers and break the offline promise the whole project rests on,
 * invisibly. The filter is absolute: when no local voice exists the feature
 * disables itself and says why rather than falling back to a remote one.
 *
 * ## Rough edges this works around
 *
 * - `getVoices()` is usually empty on first call; `voiceschanged` fires later.
 * - Chrome truncates long utterances at roughly fifteen seconds, so text is
 *   chunked by sentence and queued rather than sent as one paragraph.
 * - `pause()`/`resume()` are unreliable across browsers and are not used; stop
 *   and restart is honest and predictable.
 *
 * ## Nothing speaks at a screen you merely arrived at
 *
 * Every utterance is either a button press, or — with `autoRead` on, which is
 * off by default — a passage arriving *after* you acted inside a run: chose an
 * option, or pressed Continue. Opening a case, resuming one, or landing on the
 * debrief is always silent.
 *
 * The original rule was "no autoplay, narration starts when the learner asks
 * for it", and `autoRead` is a considered relaxation of it rather than a drift
 * away: switching the feature on is the asking, and the button was costing
 * four clicks a case that all landed on the consequence — the passage most
 * worth hearing, since you have just acted and the case is telling you what
 * happened. The part of the rule that mattered is kept exactly: the app never
 * starts talking on its own.
 */

const KEY = 'cisa.narration'

/**
 * Text cleared for narration.
 *
 * The brand is not decorative: it is the mechanism that keeps option text out
 * of the synthesiser. Only `narratable()` can mint one.
 */
export type Narratable = string & { readonly __narratable: unique symbol }

/**
 * Mark prose as narratable.
 *
 * **Call this only on `opening`, `situation`, `consequence` and an ending's
 * `narrative`.** It is deliberately not exported for general use — see
 * `narrateOpening` and friends below, which are the intended entry points and
 * name the field they read.
 */
function narratable(text: string): Narratable {
  return text as Narratable
}

/** The allow-list, as functions, so every call site names its field. */
export const narrate = {
  opening: (c: { opening: string }) => narratable(c.opening),
  situation: (n: { situation: string }) => narratable(n.situation),
  consequence: (c: { consequence: string }) => narratable(c.consequence),
  endingNarrative: (e: { narrative: string }) => narratable(e.narrative),
  /** The prompt is a question, not a comparison — safe, unlike the options. */
  prompt: (n: { prompt: string }) => narratable(n.prompt),

  /** A drill question's stem. The four options are not narratable, ever. */
  stem: (q: { stem: string }) => narratable(q.stem),

  /**
   * The explanations behind a revealed answer, as one script.
   *
   * This is the only entry that *composes* rather than forwarding a field, so
   * it is worth being explicit about why it is still safe: the parameter is a
   * `Reveal`, and a Reveal physically does not carry option text — the server
   * sends `answer`, `why_correct`, `why_wrong` and nothing else (see
   * `webapi.reveal`). There is no option text in scope here to leak.
   *
   * Options are referred to by letter, which is the whole point of doing this
   * as one utterance: "why B is wrong" is meaningless read in isolation, and
   * perfectly clear read in order with B still on the screen in front of you.
   * The screen keeps the comparison; the audio carries the reasoning.
   */
  explanations: (r: {
    answer: string
    why_correct: string
    why_wrong: Partial<Record<string, string>>
  }) => narratable([
    `Why ${r.answer} is right. ${r.why_correct}`,
    ...Object.keys(r.why_wrong)
      .sort()
      .filter((k) => k !== r.answer && r.why_wrong[k])
      .map((k) => `Why ${k} is wrong. ${r.why_wrong[k]}`),
  ].join('\n')),
} as const

export interface VoiceOption {
  name: string
  lang: string
}

export interface NarrationSettings {
  enabled: boolean
  voice: string
  rate: number
  /**
   * Read each new passage without asking, once you are inside a run.
   *
   * Off by default, and it is not autoplay even when on: the runner only
   * auto-speaks after you have chosen an option or pressed Continue, so
   * nothing ever talks at a screen you merely arrived at. Landing on a case
   * (or resuming one) stays silent until you act.
   *
   * It exists because the button costs four extra clicks per case and they all
   * land on the consequence, which is the passage most worth hearing - you
   * have just acted and the case is telling you what happened.
   */
  autoRead: boolean
}

export const DEFAULTS: NarrationSettings = {
  enabled: false, voice: '', rate: 1.05, autoRead: false,
}

export const RATES = [0.8, 1.0, 1.25, 1.5, 1.75, 2.0]

export function loadSettings(): NarrationSettings {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<NarrationSettings>
    return {
      enabled: Boolean(parsed.enabled),
      voice: typeof parsed.voice === 'string' ? parsed.voice : '',
      rate: typeof parsed.rate === 'number' && parsed.rate >= 0.5 && parsed.rate <= 3
        ? parsed.rate
        : DEFAULTS.rate,
      autoRead: Boolean(parsed.autoRead),
    }
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveSettings(s: NarrationSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s))
  } catch {
    // Private browsing, or storage full. Narration still works this session.
  }
}

export function supported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

/**
 * Local voices, in a stable order.
 *
 * `localService === true` is the whole offline guarantee. Browsers that do not
 * report the flag at all are treated as not-local: refusing to speak is the
 * safe failure, and speaking to a vendor's server is not.
 */
export function localVoices(): SpeechSynthesisVoice[] {
  if (!supported()) return []
  return window.speechSynthesis
    .getVoices()
    .filter((v) => v.localService === true)
    .sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name))
}

/** How long to keep looking for voices before giving up. */
export const VOICE_DEADLINE_MS = 6000
const VOICE_POLL_MS = 150

/**
 * Resolve the voice list, which is empty on first call in most browsers.
 *
 * **Both an event and a poll, because neither alone is reliable.** The
 * documented mechanism is `voiceschanged`, and some browsers never fire it —
 * measured here: zero voices at first call, three at 850ms, `voiceschanged`
 * not fired at all. A pure event listener waits forever on those; a fixed
 * timeout was the first fix and was wrong too, because 850ms on this machine
 * is not 850ms on a slower one, and the failure is silent — the feature simply
 * reports that no voice is installed and disables itself.
 *
 * So: resolve on the event if it comes, poll until the deadline if it does
 * not, and resolve early the moment voices appear either way.
 */
export function whenVoicesReady(): Promise<SpeechSynthesisVoice[]> {
  if (!supported()) return Promise.resolve([])
  const now = localVoices()
  if (now.length) return Promise.resolve(now)

  return new Promise((resolve) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      window.speechSynthesis.removeEventListener('voiceschanged', check)
      window.clearInterval(timer)
      resolve(localVoices())
    }
    const check = () => {
      if (localVoices().length) finish()
    }
    const timer = window.setInterval(() => {
      if (localVoices().length || Date.now() - start >= VOICE_DEADLINE_MS) finish()
    }, VOICE_POLL_MS)
    const start = Date.now()
    window.speechSynthesis.addEventListener('voiceschanged', check)
  })
}

/**
 * Split prose into utterance-sized pieces.
 *
 * Chrome cuts a long utterance off mid-word at around fifteen seconds, so the
 * text is queued as sentences. Splitting on sentence ends rather than a
 * character count keeps the prosody intact — a chunk boundary mid-clause is
 * audible and sounds like a fault.
 */
export function chunk(text: string): string[] {
  return String(text)
    .split(/\n+/)
    .flatMap((para) => para.split(/(?<=[.!?])\s+(?=[A-Z"'“])/))
    .map((s) => s.trim())
    .filter(Boolean)
}

export class Narrator {
  private settings: NarrationSettings
  private voices: SpeechSynthesisVoice[] = []
  private speaking = false
  /**
   * What is being read right now, so a button can tell whether *it* is the one
   * playing. Without this, `speaking` is narrator-wide and every button on the
   * screen flips to "Stop" together - the stem button offering to stop the
   * explanations it is not reading.
   */
  private current_text = ''
  private listeners = new Set<() => void>()

  constructor(settings: NarrationSettings = loadSettings()) {
    this.settings = settings
  }

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn)
    return () => { this.listeners.delete(fn) }
  }

  private emit(): void {
    for (const fn of this.listeners) fn()
  }

  async ready(): Promise<void> {
    this.voices = await whenVoicesReady()
    this.emit()
  }

  get available(): boolean {
    return supported() && this.voices.length > 0
  }

  /** Why the feature is off, when it is off. Shown rather than hidden. */
  get unavailableReason(): string | null {
    if (!supported()) {
      return 'This browser has no speech synthesiser, so narration is unavailable.'
    }
    if (!this.voices.length) {
      return 'No offline voice is installed on this machine. Narration only uses '
        + 'local voices — a cloud voice would send the case text to a vendor, '
        + 'which this tool does not do. Install a system voice to enable it.'
    }
    return null
  }

  get voiceOptions(): VoiceOption[] {
    return this.voices.map((v) => ({ name: v.name, lang: v.lang }))
  }

  get current(): NarrationSettings {
    return { ...this.settings }
  }

  get isSpeaking(): boolean {
    return this.speaking
  }

  /** The passage being read, or '' when silent. Compared by value. */
  get speakingText(): string {
    return this.speaking ? this.current_text : ''
  }

  update(patch: Partial<NarrationSettings>): void {
    this.settings = { ...this.settings, ...patch }
    saveSettings(this.settings)
    if (!this.settings.enabled) this.stop()
    this.emit()
  }

  private pickVoice(): SpeechSynthesisVoice | null {
    if (!this.voices.length) return null
    const named = this.voices.find((v) => v.name === this.settings.voice)
    if (named) return named
    // Prefer a voice matching the page language, then whatever is first.
    const lang = (document.documentElement.lang || 'en').slice(0, 2).toLowerCase()
    return this.voices.find((v) => v.lang.toLowerCase().startsWith(lang))
      ?? this.voices[0]
  }

  /**
   * Speak prose. Never called with option text — see the module docstring.
   *
   * Cancels anything already queued: two overlapping narrations are gibberish,
   * and the common case is the learner moving on before the last one finished.
   */
  speak(text: Narratable): void {
    if (!this.settings.enabled || !this.available) return
    const voice = this.pickVoice()
    if (!voice) return

    this.stop()
    const pieces = chunk(text)
    if (!pieces.length) return

    this.speaking = true
    this.current_text = text
    this.emit()

    pieces.forEach((piece, i) => {
      const utterance = new SpeechSynthesisUtterance(piece)
      utterance.voice = voice
      utterance.rate = this.settings.rate
      utterance.lang = voice.lang
      if (i === pieces.length - 1) {
        const finished = () => {
          this.speaking = false
          this.current_text = ''
          this.emit()
        }
        utterance.onend = finished
        utterance.onerror = finished
      }
      window.speechSynthesis.speak(utterance)
    })
  }

  /** Stop and clear the queue. Called on navigation, node change and unmount. */
  stop(): void {
    if (!supported()) return
    window.speechSynthesis.cancel()
    if (this.speaking) {
      this.speaking = false
      this.current_text = ''
      this.emit()
    }
  }
}
