/**
 * Narration controls, and the hook that owns the narrator.
 *
 * One `Narrator` per mounted case, stopped on unmount and on every node change
 * — moving to the next decision while the previous consequence is still being
 * read is the obvious bug, and it is the one users hit first.
 *
 * **Nothing speaks at a screen you merely arrived at.** Every utterance is
 * either a button press, or — with `autoRead` on, off by default — a passage
 * arriving after you acted inside a run. Opening a case, resuming one, or
 * loading the debrief is always silent. A case that starts talking on its own
 * is hostile, and browsers block it without a gesture anyway.
 *
 * The copy here claims comfort and access, never a learning benefit. Narration
 * has not been shown to improve exam performance and the exam is read silently
 * under time pressure; nothing in this interface should imply otherwise.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { narrate, Narrator, RATES, type Narratable } from '../lib/speech'
// A plain array of ids and labels - no engine code, so importing it here
// does not drag transformers.js into the main bundle.
import { NEURAL_VOICES } from '../lib/voices'

export interface NarrationHandle {
  narrator: Narrator
  available: boolean
  enabled: boolean
  autoRead: boolean
  speaking: boolean
  /** The passage currently being read, so a button knows if it is the one. */
  speakingText: string
  /** Kokoro state, for the picker and the loading line. */
  neural: {
    available: boolean      // weights on disk
    ready: boolean          // weights in memory
    loading: boolean
    progress: number
    problem: string
    backend: string
  }
  reason: string | null
  say: (text: Narratable) => void
  stop: () => void
}

/**
 * `key` is whatever identifies the current node; speech stops whenever it
 * changes. Passing the node id means a decision cannot be narrated over the
 * consequence of the last one.
 */
export function useNarration(key: unknown): NarrationHandle {
  const ref = useRef<Narrator | null>(null)
  if (ref.current === null) ref.current = new Narrator()
  const narrator = ref.current
  const [, force] = useState(0)

  useEffect(() => {
    const unsubscribe = narrator.subscribe(() => force((n) => n + 1))
    void narrator.ready()
    return () => {
      unsubscribe()
      narrator.stop()      // unmount
    }
  }, [narrator])

  useEffect(() => {
    narrator.stop()        // node change
  }, [key, narrator])

  const say = useCallback((text: Narratable) => narrator.speak(text), [narrator])
  const stop = useCallback(() => narrator.stop(), [narrator])

  return {
    narrator,
    available: narrator.available,
    enabled: narrator.current.enabled,
    autoRead: narrator.current.autoRead,
    speaking: narrator.isSpeaking,
    speakingText: narrator.speakingText,
    neural: {
      available: narrator.neuralAvailable,
      ready: narrator.neuralReady,
      loading: narrator.neuralBusy,
      progress: narrator.neuralLoadProgress,
      problem: narrator.neuralProblem,
      backend: narrator.neuralBackend,
    },
    reason: narrator.unavailableReason,
    say,
    stop,
  }
}

/**
 * Audition the selected voice, and warm the engine while you are at it.
 *
 * The neural engine's cost is almost entirely the one-off session build, not
 * the synthesis. Paying it here - on a settings screen, while you are choosing
 * anyway - moves it out of the moment when you actually want to hear a
 * question.
 *
 * The progress number is real. Inference runs in a worker, so React can
 * repaint while the session builds - verified with the Long Task API, which
 * reports zero main-thread tasks over 50ms through a cold load and a full
 * synthesis. An earlier version of this comment claimed a measured 1.2s
 * freeze on the main thread; that number came from a timer poll in a hidden
 * tab, where timers are throttled to about 1/second, so it did not show what
 * it was said to show.
 */
function PreviewButton({ n }: { n: NarrationHandle }) {
  const settings = n.narrator.current
  const sample = narrate.sample()
  const playing = n.speakingText === sample
  const warming = n.neural.loading
  const neural = settings.engine === 'neural'

  return (
    <button type="button" className="btn small"
            disabled={warming}
            onClick={() => (playing ? n.stop() : n.say(sample))}>
      {warming
        ? `Loading the voice… ${Math.round(n.neural.progress * 100)}%`
        : playing
          ? 'Stop'
          : neural && !n.neural.ready
            ? 'Hear this voice (loads it first)'
            : 'Hear this voice'}
    </button>
  )
}

/** A single "read this aloud" button, sitting beside the prose it reads. */
export function SpeakButton({ n, text, label = 'Read aloud' }: {
  n: NarrationHandle
  text: Narratable
  label?: string
}) {
  if (!n.available || !n.enabled) return null
  // Only the button whose own passage is playing offers to stop it. `speaking`
  // alone is narrator-wide, which turned every button on the screen into
  // "Stop" at once - the stem offering to stop the explanations.
  const mine = n.speakingText === text
  return (
    <button type="button" className="speak-btn"
            onClick={() => (mine ? n.stop() : n.say(text))}
            aria-label={mine ? 'Stop reading' : label}>
      {mine ? (
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M11 5L6 9H3v6h3l5 4V5z" />
          <path d="M15.5 8.5a5 5 0 010 7" />
          <path d="M18.5 5.5a9 9 0 010 13" />
        </svg>
      )}
      <span>{mine ? 'Stop' : label}</span>
    </button>
  )
}

/**
 * The settings row: on/off, voice, rate.
 *
 * `kind` changes the copy and hides the auto-read toggle on drills, because
 * auto-read is a case behaviour and does not apply here. Showing a switch on
 * the drill screen that changes nothing about drills would be a small lie, and
 * the setting itself is shared - turning narration on in either place turns it
 * on in both, since it is one stored preference.
 */
export function NarrationControls({ n, kind = 'case' }: {
  n: NarrationHandle
  kind?: 'case' | 'drill'
}) {
  const settings = n.narrator.current
  const voices = n.narrator.voiceOptions
  const isDrill = kind === 'drill'

  if (n.reason) {
    return (
      <div className="narration-off">
        <b>Narration unavailable.</b> {n.reason}
      </div>
    )
  }

  return (
    <div className="narration">
      <label className="narration-toggle">
        <input type="checkbox" checked={settings.enabled}
               onChange={(ev) => n.narrator.update({ enabled: ev.target.checked })} />
        <span>{isDrill ? 'Read questions aloud' : 'Read cases aloud'}</span>
      </label>

      {settings.enabled ? (
        <>
          {settings.engine === 'system' ? (
            <label className="narration-field">
              <span>Voice</span>
              <select value={settings.voice}
                      onChange={(ev) => n.narrator.update({ voice: ev.target.value })}>
                <option value="">Default ({voices[0]?.name ?? 'none'})</option>
                {voices.map((v) => (
                  <option key={v.name} value={v.name}>{v.name} — {v.lang}</option>
                ))}
              </select>
            </label>
          ) : null}

          <label className="narration-field">
            <span>Engine</span>
            <select value={settings.engine}
                    onChange={(ev) => n.narrator.update({
                      engine: ev.target.value === 'neural' ? 'neural' : 'system',
                    })}>
              <option value="system">System voices</option>
              <option value="neural" disabled={!n.neural.available}>
                Neural{n.neural.available ? '' : ' — not downloaded'}
              </option>
            </select>
          </label>

          {settings.engine === 'neural' ? (
            <label className="narration-field">
              <span>Voice</span>
              <select value={settings.neuralVoice}
                      onChange={(ev) => n.narrator.update({ neuralVoice: ev.target.value })}>
                {NEURAL_VOICES.map((v) => (
                  <option key={v.id} value={v.id}>{v.label}</option>
                ))}
              </select>
            </label>
          ) : null}

          {/*
            Auditioning a voice here does double duty. It is the only way to
            tell thirteen names apart without committing to a session - and it
            builds the 92MB inference session, which is the slow part. Do it on
            this screen and the first press inside a drill is instant instead
            of a long silence with a dead button.
          */}
          <PreviewButton n={n} />

          <label className="narration-field">
            <span>Speed</span>
            <select value={String(settings.rate)}
                    onChange={(ev) => n.narrator.update({ rate: Number(ev.target.value) })}>
              {RATES.map((r) => (
                <option key={r} value={String(r)}>{r}×</option>
              ))}
            </select>
          </label>

          {/* Cases only: a drill has no passage that arrives after you act. */}
          {isDrill ? null : (
            <label className="narration-toggle">
              <input type="checkbox" checked={settings.autoRead}
                     onChange={(ev) => n.narrator.update({ autoRead: ev.target.checked })} />
              <span>Read each passage automatically</span>
            </label>
          )}
        </>
      ) : null}

      {settings.enabled && settings.engine === 'neural' ? (
        <div className="narration-neural">
          {n.neural.problem ? (
            <span className="bad">
              The neural voice failed to load: {n.neural.problem}. Switch back to
              system voices, or re-run <code>python get_voices.py --check</code>.
            </span>
          ) : n.neural.loading ? (
            <>
              <span className="spinner" />
              Loading the voice model — {Math.round(n.neural.progress * 100)}%.
              About 92&nbsp;MB, once per session; it plays as soon as it is in.
            </>
          ) : n.neural.ready ? (
            <span className="good">
              Neural voice ready{n.neural.backend
                ? ` on ${n.neural.backend.startsWith('webgpu')
                    ? 'your GPU' : 'the CPU'}`
                : ''}. Synthesis happens on this machine.
            </span>
          ) : (
            <>
              Not loaded yet. The first play builds a 92&nbsp;MB inference
              session, once per session. It runs on a background thread, so the
              page stays usable while it happens — but doing it here, now,
              means the drill itself starts without any wait.
            </>
          )}
        </div>
      ) : null}

      {settings.enabled && !n.neural.available ? (
        <div className="narration-neural">
          Better voices are available and free. The system voices on Windows are
          a decade old; Kokoro-82M runs locally and sounds far better. One
          download, then it is offline like everything else:
          {' '}<code>python get_voices.py</code>
        </div>
      ) : null}

      <p className="narration-note">
        {voices.length} offline {voices.length === 1 ? 'voice' : 'voices'} on this
        machine. Cloud voices are never used, so nothing you hear leaves it —
        that holds for the neural engine too: the weights sit on your disk and
        synthesis runs in this browser.
        {isDrill
          ? ' The stem and the explanations are read; the four options are not '
            + '— they are meant to be compared side by side, which listening '
            + 'makes harder. Explanations name the options by letter.'
          : ' The narrative is read; the options are not — they are meant to be '
            + 'compared side by side, which listening makes harder.'}
        {isDrill
          ? ' Nothing reads itself here; every passage is a button.'
          : null}
        {!isDrill && settings.enabled && settings.autoRead ? (
          <>
            {' '}Automatic reading starts only once you are moving through a case:
            choosing an option or pressing Continue. Opening or resuming a case
            stays silent.
          </>
        ) : null}
      </p>
    </div>
  )
}
