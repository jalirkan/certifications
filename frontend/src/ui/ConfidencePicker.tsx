/**
 * Confidence capture.
 *
 * Three levels, mandatory, taken with the answer. Not a slider and not a
 * percentage: people cannot produce calibrated numbers without training, and a
 * coarse scale answered honestly beats a fine one answered carelessly.
 *
 * The ordering matters. Answer first (`A`–`D`), then rate (`1`–`3`), and only
 * then does the reveal happen — confidence recorded after seeing the result
 * would be hindsight, which is worth nothing. That constraint, not the visual
 * design, is why this is a separate step rather than a checkbox on the option.
 */

import type { Confidence } from '../api/types'

export const CONFIDENCE_META: {
  level: Exclude<Confidence, ''>
  key: string
  label: string
  gloss: string
}[] = [
  { level: 'guess', key: '1', label: 'Guess', gloss: 'no better than picking' },
  { level: 'unsure', key: '2', label: 'Unsure', gloss: 'leaning one way, could not defend it' },
  { level: 'confident', key: '3', label: 'Confident', gloss: 'would defend this in a review' },
]

export function ConfidencePicker({
  value, onPick, disabled, compact,
}: {
  value: Confidence
  onPick: (level: Exclude<Confidence, ''>) => void
  disabled?: boolean
  compact?: boolean
}) {
  return (
    <div className={`confidence ${compact ? 'compact' : ''}`.trim()}>
      <div className="confidence-label">
        How sure are you? <span className="dim">recorded before you see the answer</span>
      </div>
      <div className="confidence-row" role="group" aria-label="Confidence">
        {CONFIDENCE_META.map((c) => (
          <button
            key={c.level}
            type="button"
            className={`conf-btn ${value === c.level ? 'on' : ''}`.trim()}
            disabled={disabled}
            aria-pressed={value === c.level}
            onClick={() => onPick(c.level)}
          >
            <span className="k">{c.key}</span>
            <span className="t">{c.label}</span>
            {!compact ? <span className="g">{c.gloss}</span> : null}
          </button>
        ))}
      </div>
    </div>
  )
}

/** Small read-only badge for review screens. */
export function ConfidenceChip({ value }: { value: Confidence }) {
  if (!value) return <span className="chip">not rated</span>
  const tone = value === 'confident' ? 'bad' : ''
  return <span className={`chip ${tone}`.trim()}>{value}</span>
}
