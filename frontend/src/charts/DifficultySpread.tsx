/**
 * Difficulty distribution of the bank, from item analysis.
 *
 * This describes the *questions*, not the user. A bank with everything bunched
 * at "easy" is not testing much, and one bunched at "very hard" usually means
 * badly written items rather than a hard subject.
 */

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { C } from './theme'

/*
 * The server labels buckets "very hard <25%", "hard 25-50%" and so on. Matching
 * on the leading word rather than the whole label means a change to the
 * threshold text does not silently drop the colour coding.
 *
 * p-value is proportion correct, so higher is easier. "Trivial" is greyed
 * rather than green: a question everyone gets right is not a good question.
 */
const HUE: { prefix: string; color: string }[] = [
  { prefix: 'very hard', color: C.bad },
  { prefix: 'hard', color: C.warn },
  { prefix: 'moderate', color: C.accent },
  { prefix: 'easy', color: C.good },
  { prefix: 'trivial', color: C.mute },
]

function hueFor(bucket: string): string {
  const key = bucket.toLowerCase()
  // Longest prefix first so "very hard" is not swallowed by "hard".
  const hit = [...HUE].sort((a, b) => b.prefix.length - a.prefix.length)
    .find((h) => key.startsWith(h.prefix))
  return hit?.color ?? C.accent
}

function SpreadTip({ active, payload }: {
  active?: boolean
  payload?: { payload: { bucket: string; count: number; share: number } }[]
}) {
  if (!active || !payload?.length) return null
  const p = payload[0].payload
  return (
    <div className="tip">
      <div className="t">{p.bucket}</div>
      <div className="s">
        {p.count} questions · {Math.round(p.share * 100)}% of those with statistics
      </div>
    </div>
  )
}

export function DifficultySpread({
  spread, withStats,
}: {
  spread: Record<string, number>
  withStats: number
}) {
  // The server emits the buckets already ordered hardest to easiest.
  const data = Object.keys(spread).map((bucket) => ({
    bucket,
    count: spread[bucket] ?? 0,
    share: withStats ? (spread[bucket] ?? 0) / withStats : 0,
  }))

  if (!withStats) {
    return (
      <p className="chart-note">
        No question has enough attempts yet to place it on a difficulty scale.
      </p>
    )
  }

  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 8, right: 14, bottom: 4, left: -18 }}>
          <XAxis dataKey="bucket" tick={{ fill: C.mute, fontSize: 11 }} stroke={C.line} />
          <YAxis tick={{ fill: C.mute, fontSize: 11 }} stroke={C.line} allowDecimals={false} />
          <Tooltip content={<SpreadTip />} cursor={{ fill: 'rgba(255,255,255,.03)' }} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.bucket} fill={hueFor(d.bucket)} fillOpacity={0.8} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <p className="chart-note">
        Based on {withStats} questions with enough attempts to judge. This is a
        property of the bank, not of you.
      </p>
    </div>
  )
}
