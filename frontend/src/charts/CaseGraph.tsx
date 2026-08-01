/**
 * The case as a map: every decision, every branch, and where yours went.
 *
 * The debrief already lists the options node by node. This draws the shape they
 * came from, which is the part that cannot be held in the head — you walked one
 * thread through a graph, and the threads you did not walk are most of the
 * teaching.
 *
 * The payoff is not the branching, which is modest. It is the override edge:
 * when a taint fired, your path visibly continues toward one ending while a red
 * line drags the outcome to another. "You were finished four decisions ago" is
 * a paragraph in text and about a second as a picture.
 *
 * **No graph library.** The cases are 5–8 nodes, depth 5–7, and at most three
 * wide. Longest-path layering plus one barycentre pass is forty lines and gives
 * a better result here than a general-purpose layout engine, which would spend
 * its cleverness on a problem these graphs do not have. Cases are validated
 * acyclic, so the layering always terminates.
 *
 * Laid out **top to bottom** rather than left to right: depth runs to 7, width
 * never past 3, so vertical scrolling is natural and the whole thing fits a
 * narrow column without horizontal scroll.
 */

import { useMemo, useState } from 'react'
import type { CaseGraph as Graph, CaseGraphEdge } from '../api/types'
import { C } from './theme'

const NODE_W = 190
const NODE_H = 46
const COL_GAP = 34
const ROW_GAP = 62
const PAD = 16

const VERDICT_HUE: Record<string, string> = {
  strong: C.good,
  acceptable: C.accent,
  weak: C.warn,
  failed: C.bad,
}

const QUALITY_HUE: Record<string, string> = {
  best: C.good,
  defensible: C.dim,
  poor: C.bad,
}

interface Placed {
  id: string
  kind: 'node' | 'ending'
  label: string
  sub: string
  depth: number
  x: number
  y: number
  walked: boolean
  position: number
  verdict?: string
  reached?: boolean
  graphReached?: boolean
}

/**
 * Longest-path layering.
 *
 * Longest rather than shortest so a node never sits above something that can
 * reach it — with shortest paths, a branch that rejoins late would be drawn
 * pointing backwards.
 */
function layer(graph: Graph): Map<string, number> {
  const outgoing = new Map<string, string[]>()
  for (const e of graph.edges) {
    if (!outgoing.has(e.from)) outgoing.set(e.from, [])
    outgoing.get(e.from)!.push(e.to)
  }
  const depth = new Map<string, number>()
  const visit = (id: string, d: number, seen: Set<string>) => {
    if (seen.has(id)) return          // validated acyclic; belt and braces
    depth.set(id, Math.max(depth.get(id) ?? 0, d))
    for (const next of outgoing.get(id) ?? []) {
      visit(next, d + 1, new Set(seen).add(id))
    }
  }
  visit(graph.start, 0, new Set())
  return depth
}

function place(graph: Graph): { placed: Placed[]; width: number; height: number } {
  const depth = layer(graph)
  const byId = new Map<string, Placed>()

  for (const n of graph.nodes) {
    byId.set(n.id, {
      id: n.id, kind: 'node', label: n.prompt, sub: n.id,
      depth: depth.get(n.id) ?? 0, x: 0, y: 0,
      walked: n.walked, position: n.position,
    })
  }
  for (const e of graph.endings) {
    byId.set(e.id, {
      id: e.id, kind: 'ending', label: e.title, sub: e.verdict || 'ending',
      depth: depth.get(e.id) ?? 0, x: 0, y: 0,
      walked: e.reached, position: 0,
      verdict: e.verdict, reached: e.reached, graphReached: e.graph_reached,
    })
  }

  // Unreachable nodes have no depth; validation warns about them separately,
  // and dropping them here would hide a real authoring mistake.
  const layers = new Map<number, Placed[]>()
  for (const p of byId.values()) {
    if (!layers.has(p.depth)) layers.set(p.depth, [])
    layers.get(p.depth)!.push(p)
  }

  // One barycentre pass: order each layer by the average position of whatever
  // points into it, which removes most crossings on graphs this size.
  const incoming = new Map<string, string[]>()
  for (const e of graph.edges) {
    if (!incoming.has(e.to)) incoming.set(e.to, [])
    incoming.get(e.to)!.push(e.from)
  }
  const orderIn = new Map<string, number>()
  const depths = [...layers.keys()].sort((a, b) => a - b)
  for (const d of depths) {
    const row = layers.get(d)!
    row.sort((a, b) => {
      const bary = (p: Placed) => {
        const parents = incoming.get(p.id) ?? []
        if (!parents.length) return 0
        const sum = parents.reduce((s, id) => s + (orderIn.get(id) ?? 0), 0)
        return sum / parents.length
      }
      return bary(a) - bary(b) || a.id.localeCompare(b.id)
    })
    row.forEach((p, i) => orderIn.set(p.id, i))
  }

  const widest = Math.max(...[...layers.values()].map((r) => r.length), 1)
  const width = PAD * 2 + widest * NODE_W + (widest - 1) * COL_GAP
  const height = PAD * 2 + depths.length * NODE_H
    + (depths.length - 1) * (ROW_GAP - NODE_H) + ROW_GAP

  for (const d of depths) {
    const row = layers.get(d)!
    const rowWidth = row.length * NODE_W + (row.length - 1) * COL_GAP
    const left = (width - rowWidth) / 2
    row.forEach((p, i) => {
      p.x = left + i * (NODE_W + COL_GAP)
      p.y = PAD + depths.indexOf(d) * ROW_GAP
    })
  }

  return { placed: [...byId.values()], width, height }
}

function truncate(text: string, n: number): string {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text
}

export function CaseGraph({ graph }: { graph: Graph }) {
  const { placed, width, height } = useMemo(() => place(graph), [graph])
  const [selected, setSelected] = useState<string | null>(null)

  const at = useMemo(() => {
    const m = new Map<string, Placed>()
    for (const p of placed) m.set(p.id, p)
    return m
  }, [placed])

  const edgePath = (from: string, to: string) => {
    const a = at.get(from)
    const b = at.get(to)
    if (!a || !b) return null
    const x1 = a.x + NODE_W / 2
    const y1 = a.y + NODE_H
    const x2 = b.x + NODE_W / 2
    const y2 = b.y
    const mid = (y1 + y2) / 2
    return `M ${x1} ${y1} C ${x1} ${mid}, ${x2} ${mid}, ${x2} ${y2}`
  }

  const selectedNode = selected ? at.get(selected) : null

  // A decision shows what it leads to; an ending shows what leads to it —
  // "which choices land here" is the question an ending actually raises.
  const detail = !selectedNode
    ? []
    : selectedNode.kind === 'ending'
      ? graph.edges.filter((e) => e.to === selected)
      : graph.edges.filter((e) => e.from === selected)

  return (
    <div className="case-graph">
      <div className="cg-canvas" style={{ maxWidth: width }}>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="The whole case as a decision graph, with the path taken highlighted"
           style={{ display: 'block' }}>
        <defs>
          <marker id="cg-arrow" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" fill={C.line} />
          </marker>
          <marker id="cg-arrow-on" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" fill={C.accent} />
          </marker>
          <marker id="cg-arrow-bad" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L8 4 L0 8 z" fill={C.bad} />
          </marker>
        </defs>

        {/* Branches not taken first, so the walked path draws over them. */}
        {graph.edges.filter((e) => !e.chosen).map((e, i) => {
          const d = edgePath(e.from, e.to)
          if (!d) return null
          return (
            <path key={`u${i}`} d={d} fill="none" stroke={C.line} strokeWidth={1}
                  markerEnd="url(#cg-arrow)" opacity={0.55} />
          )
        })}

        {graph.edges.filter((e) => e.chosen).map((e, i) => {
          const d = edgePath(e.from, e.to)
          if (!d) return null
          return (
            <path key={`c${i}`} d={d} fill="none" stroke={C.accent}
                  strokeWidth={2.4} markerEnd="url(#cg-arrow-on)" />
          )
        })}

        {/* The edge that fixed the outcome. Not one of the case's own edges -
            it is what the taint did to the path, so it is drawn differently. */}
        {graph.override ? (() => {
          const d = edgePath(graph.override.from, graph.override.to)
          if (!d) return null
          return (
            <path d={d} fill="none" stroke={C.bad} strokeWidth={2.6}
                  strokeDasharray="7 4" markerEnd="url(#cg-arrow-bad)" />
          )
        })() : null}

        {placed.map((p) => {
          const isEnding = p.kind === 'ending'
          const hue = isEnding ? (VERDICT_HUE[p.verdict ?? ''] ?? C.mute) : C.accent
          const active = p.walked || p.reached
          const focused = selected === p.id
          return (
            <g key={p.id} className="cg-node" aria-hidden="true">
              <rect x={p.x} y={p.y} width={NODE_W} height={NODE_H} rx={7}
                    fill={active ? 'rgba(77,208,199,.10)' : C.surface}
                    stroke={focused ? C.text : (active ? hue : C.line)}
                    strokeWidth={focused ? 2 : active ? 1.8 : 1}
                    strokeDasharray={p.graphReached ? '5 3' : undefined} />
              {p.position ? (
                <circle cx={p.x + 13} cy={p.y + 13} r={8} fill={C.accent} />
              ) : null}
              {p.position ? (
                <text x={p.x + 13} y={p.y + 16.5} textAnchor="middle"
                      fontSize={10} fill="#06231f" fontWeight={700}>
                  {p.position}
                </text>
              ) : null}
              <text x={p.x + (p.position ? 27 : 11)} y={p.y + 18}
                    fontSize={11.5} fill={active ? C.text : C.dim}>
                {truncate(p.label, isEnding ? 24 : 22)}
              </text>
              <text x={p.x + 11} y={p.y + 34} fontSize={10}
                    fill={isEnding ? hue : C.mute}>
                {isEnding
                  ? `${p.verdict}${p.reached ? ' — your ending' : ''}${
                      p.graphReached ? ' — where the graph led' : ''}`
                  : truncate(p.sub, 30)}
              </text>
            </g>
          )
        })}
      </svg>

      {/*
        The hit targets are real HTML buttons laid over the drawing, not the
        SVG shapes themselves. `<g tabindex="0">` is focusable in Chrome and
        Firefox and not in Safari, and screen readers treat SVG children
        inconsistently even where focus works — so the picture stays a picture
        (`role="img"`, children `aria-hidden`) and every box gets a button.
        Positions are percentages of the viewBox, so they track the SVG through
        any amount of scaling without a resize listener.
      */}
      <div className="cg-hit">
        {placed.map((p) => (
          <button key={p.id} type="button"
                  className={`cg-hit-btn${selected === p.id ? ' on' : ''}`}
                  style={{
                    left: `${(p.x / width) * 100}%`,
                    top: `${(p.y / height) * 100}%`,
                    width: `${(NODE_W / width) * 100}%`,
                    height: `${(NODE_H / height) * 100}%`,
                  }}
                  aria-pressed={selected === p.id}
                  onMouseEnter={() => setSelected(p.id)}
                  onFocus={() => setSelected(p.id)}
                  onClick={() => setSelected(p.id)}>
            {p.kind === 'ending' ? 'Ending' : 'Decision'}
            {p.position ? ` ${p.position}` : ''}: {p.label}
            {p.kind === 'ending' ? ` — ${p.verdict}` : ''}
            {p.reached ? ' — your ending' : ''}
            {p.graphReached ? ' — where the graph led before the taint' : ''}
            {p.kind === 'node' && !p.walked ? ' — never reached' : ''}
          </button>
        ))}
      </div>
      </div>

      <div className="cg-legend">
        <span className="k"><i style={{ background: C.accent }} />your path</span>
        <span className="k"><i style={{ background: C.line }} />not taken</span>
        {graph.override ? (
          <span className="k"><i style={{ background: C.bad }} />the taint that decided it</span>
        ) : null}
        <span className="k"><i style={{ background: C.good }} />strong</span>
        <span className="k"><i style={{ background: C.warn }} />weak</span>
        <span className="k"><i style={{ background: C.bad }} />failed</span>
      </div>

      {selectedNode ? (
        <div className="cg-detail">
          <div className="cg-detail-head">
            {selectedNode.kind === 'ending' ? (
              <span className="chip">
                {selectedNode.reached ? 'your ending' : 'ending not reached'}
              </span>
            ) : selectedNode.position ? (
              <span className="chip">decision {selectedNode.position}</span>
            ) : (
              <span className="chip">never reached</span>
            )}
            <b>{selectedNode.label}</b>
          </div>

          {/* Some endings have no edge into them at all: they exist only as
              somewhere a taint can force you. Left blank, that reads as a bug
              rather than as the point. */}
          {selectedNode.kind === 'ending' && !detail.length ? (
            <p className="chart-note">
              No choice in this case leads here. It is reachable only when a
              decision has already fixed the outcome
              {graph.override && graph.override.to === selectedNode.id
                ? ` — yours did, at decision ${graph.override.decision}.`
                : '.'}
            </p>
          ) : null}

          <div className="list">
            {detail.map((e: CaseGraphEdge) => (
              <div className="list-row" key={`${e.from}:${e.key}`}>
                <span className={`chip ${e.chosen ? '' : 'dim'}`.trim()}>{e.key}</span>
                <div className="grow">
                  <div className="t">{e.text}</div>
                  <div className="s">
                    <span style={{ color: QUALITY_HUE[e.quality] ?? C.mute }}>
                      {e.quality}
                    </span>
                    {e.chosen ? ' · you chose this' : ''}
                    {e.taint ? ` · unrecoverable (${e.taint})` : ''}
                    {selectedNode.kind === 'ending'
                      ? ` · from ${e.from}`
                      : ` · leads to ${e.to}`}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="chart-note">
          Hover or tab through the boxes to see the options at each decision,
          and what leads to each ending.
        </p>
      )}
    </div>
  )
}
