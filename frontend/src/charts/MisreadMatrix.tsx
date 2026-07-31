/**
 * Cold Read misreads: what the question was asking, against how it was read.
 *
 * A heatmap rather than a list because the interesting structure is directional.
 * "Asked for a control, read as a risk" is a different habit from the reverse,
 * and they sit in opposite cells here. Clusters in a row mean one question type
 * is being systematically misread; a cluster in a column means one reading is
 * being over-applied.
 *
 * Hand-built SVG: the matrix is small, sparse and needs both axes labelled with
 * full ask-type names, which a generic heatmap component makes harder, not
 * easier.
 */

import { useState } from 'react'
import type { AskType, GameStats } from '../api/types'
import { C, useWidth } from './theme'

const CELL_MIN = 34
const LEFT = 128
const TOP = 78

export function MisreadMatrix({
  stats, askTypes,
}: {
  stats: GameStats
  askTypes: AskType[]
}) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<{ e: string; r: string; n: number } | null>(null)

  if (!stats.misreads.length) {
    return (
      <p className="chart-note">
        No misreads recorded yet. Play Cold Read and this fills in with the
        question types you mistake for each other.
      </p>
    )
  }

  // Only show ask types that actually appear, so the grid stays legible.
  const involved = new Set<string>()
  for (const m of stats.misreads) {
    involved.add(m.expected)
    involved.add(m.read)
  }
  const types = askTypes.filter((t) => involved.has(t.id))
  const labels = types.length ? types : [...involved].map((id) => ({ id, label: id, gloss: '' }))

  const counts = new Map<string, number>()
  for (const m of stats.misreads) counts.set(`${m.expected}|${m.read}`, m.count)
  const max = Math.max(...stats.misreads.map((m) => m.count), 1)

  const cell = Math.max(CELL_MIN, Math.min(56, (width - LEFT - 16) / labels.length || CELL_MIN))
  const gridW = cell * labels.length
  const height = TOP + cell * labels.length + 16

  return (
    <div className="chart-wrap" ref={ref} style={{ position: 'relative', overflowX: 'auto' }}>
      <svg width={Math.max(width, LEFT + gridW + 16)} height={height} role="img"
           aria-label="Matrix of question types against how they were read">
        {/* column headers, angled so long labels fit */}
        {labels.map((t, c) => (
          <text
            key={t.id}
            x={LEFT + c * cell + cell / 2}
            y={TOP - 8}
            transform={`rotate(-38 ${LEFT + c * cell + cell / 2} ${TOP - 8})`}
            fontSize={11}
            fill={C.dim}
            textAnchor="start"
          >
            {t.label}
          </text>
        ))}

        {labels.map((rowType, r) => (
          <g key={rowType.id}>
            <text x={LEFT - 9} y={TOP + r * cell + cell / 2 + 4} textAnchor="end"
                  fontSize={11} fill={C.dim}>
              {rowType.label}
            </text>
            {labels.map((colType, c) => {
              const n = counts.get(`${rowType.id}|${colType.id}`) ?? 0
              const diagonal = rowType.id === colType.id
              const intensity = n / max
              return (
                <rect
                  key={colType.id}
                  x={LEFT + c * cell + 1}
                  y={TOP + r * cell + 1}
                  width={cell - 2}
                  height={cell - 2}
                  rx={3}
                  fill={
                    diagonal
                      ? 'transparent'
                      : n
                        ? `rgba(242, 97, 90, ${0.14 + intensity * 0.66})`
                        : C.raised
                  }
                  stroke={diagonal ? C.line : 'none'}
                  strokeDasharray={diagonal ? '3 3' : undefined}
                  onMouseEnter={() =>
                    n && setHover({ e: rowType.label, r: colType.label, n })
                  }
                  onMouseLeave={() => setHover(null)}
                />
              )
            })}
          </g>
        ))}

        {/* counts on top of the cells that have any */}
        {labels.map((rowType, r) =>
          labels.map((colType, c) => {
            const n = counts.get(`${rowType.id}|${colType.id}`) ?? 0
            if (!n || rowType.id === colType.id) return null
            return (
              <text
                key={`${rowType.id}-${colType.id}`}
                x={LEFT + c * cell + cell / 2}
                y={TOP + r * cell + cell / 2 + 4}
                textAnchor="middle"
                fontSize={11.5}
                fill={C.text}
                pointerEvents="none"
              >
                {n}
              </text>
            )
          }),
        )}

        <text x={LEFT} y={16} fontSize={11} fill={C.mute}>read as →</text>
        <text x={6} y={TOP + 4} fontSize={11} fill={C.mute}>was asking ↓</text>
      </svg>

      {hover ? (
        <div className="tip" style={{ position: 'absolute', right: 8, top: 8, pointerEvents: 'none' }}>
          <div className="t">{hover.n}× misread</div>
          <div className="s">
            asked for <b>{hover.e}</b>, read as <b>{hover.r}</b>
          </div>
        </div>
      ) : null}

      <p className="chart-note">
        Rows are what the question asked for; columns are how you read it. The
        diagonal is a correct read and is left blank.
      </p>
    </div>
  )
}
