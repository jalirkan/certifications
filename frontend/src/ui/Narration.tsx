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
import { Narrator, RATES, type Narratable } from '../lib/speech'

export interface NarrationHandle {
  narrator: Narrator
  available: boolean
  enabled: boolean
  autoRead: boolean
  speaking: boolean
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
    reason: narrator.unavailableReason,
    say,
    stop,
  }
}

/** A single "read this aloud" button, sitting beside the prose it reads. */
export function SpeakButton({ n, text, label = 'Read aloud' }: {
  n: NarrationHandle
  text: Narratable
  label?: string
}) {
  if (!n.available || !n.enabled) return null
  return (
    <button type="button" className="speak-btn"
            onClick={() => (n.speaking ? n.stop() : n.say(text))}
            aria-label={n.speaking ? 'Stop reading' : label}>
      {n.speaking ? (
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
             strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M11 5L6 9H3v6h3l5 4V5z" />
          <path d="M15.5 8.5a5 5 0 010 7" />
          <path d="M18.5 5.5a9 9 0 010 13" />
        </svg>
      )}
      <span>{n.speaking ? 'Stop' : label}</span>
    </button>
  )
}

/** The settings row: on/off, voice, rate. Shown on the case list screen. */
export function NarrationControls({ n }: { n: NarrationHandle }) {
  const settings = n.narrator.current
  const voices = n.narrator.voiceOptions

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
        <span>Read cases aloud</span>
      </label>

      {settings.enabled ? (
        <>
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

          <label className="narration-field">
            <span>Speed</span>
            <select value={String(settings.rate)}
                    onChange={(ev) => n.narrator.update({ rate: Number(ev.target.value) })}>
              {RATES.map((r) => (
                <option key={r} value={String(r)}>{r}×</option>
              ))}
            </select>
          </label>

          <label className="narration-toggle">
            <input type="checkbox" checked={settings.autoRead}
                   onChange={(ev) => n.narrator.update({ autoRead: ev.target.checked })} />
            <span>Read each passage automatically</span>
          </label>
        </>
      ) : null}

      <p className="narration-note">
        {voices.length} offline {voices.length === 1 ? 'voice' : 'voices'} on this
        machine. Cloud voices are never used, so nothing you hear leaves it.
        The narrative is read; the options are not — they are meant to be
        compared side by side, which listening makes harder.
        {settings.enabled && settings.autoRead ? (
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
