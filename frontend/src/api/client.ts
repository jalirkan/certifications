/**
 * Transport for the local Python API.
 *
 * Same origin, no auth, profile selected by an X-Profile header. Nothing here
 * caches question payloads: the server is on localhost and re-fetching is
 * cheap, whereas a client-side cache of answered questions is exactly the kind
 * of thing that turns devtools into a cheat menu.
 */

import type {
  AutopsyResult, Bootstrap, Calibration, CaseChoice, CaseDebrief, CaseListEntry,
  CaseState, ColdReadResult, Confidence, DrillAvailability, DrillStart,
  DrillStartParams,
  ExamResult, ExamState, ExamSummary, GameName, GameStart, GameStats, Items,
  Letter, Overview, Reveal, Trend,
} from './types'

/** Set by the profile provider; read on every request. */
let currentProfile = ''

export function setProfile(profile: string): void {
  currentProfile = profile || ''
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { 'X-Profile': currentProfile }
  if (init?.body) headers['Content-Type'] = 'application/json'

  let res: Response
  try {
    res = await fetch(path, { ...init, headers: { ...headers, ...init?.headers } })
  } catch {
    // The server is local, so this almost always means it was stopped.
    throw new ApiError('Could not reach the study server. Is python serve.py still running?', 0)
  }

  let data: unknown = null
  try {
    data = await res.json()
  } catch {
    data = null
  }

  if (!res.ok) {
    const message =
      data && typeof data === 'object' && 'error' in data
        ? String((data as { error: unknown }).error)
        : `Request failed (${res.status})`
    throw new ApiError(message, res.status)
  }
  return data as T
}

const get = <T>(path: string) => request<T>(path)
const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body ?? {}) })

export const api = {
  bootstrap: () => get<Bootstrap>('/api/bootstrap'),
  overview: () => get<Overview>('/api/overview'),
  trend: (days = 90, window = 7) =>
    get<Trend>(`/api/trend?days=${days}&window=${window}`),
  items: (min = 5) => get<Items>(`/api/items?min=${min}`),
  card: () => get<{ text: string }>('/api/card'),

  drillStart: (params: DrillStartParams) =>
    post<DrillStart>('/api/drill/start', params),
  /** Availability for the current filters, so a short or empty pool is shown
   *  before the learner commits rather than discovered mid-session. */
  drillPreview: (params: DrillStartParams) =>
    post<DrillAvailability>('/api/drill/preview', params),
  drillAnswer: (body: {
    question_id: string
    chosen: Letter
    session: string
    mode: string
    seconds: number
    /** Sent with the answer so it is recorded before the reveal. */
    confidence: Confidence
  }) => post<Reveal>('/api/drill/answer', body),

  gameStart: (game: GameName, n: number) =>
    post<GameStart>('/api/game/start', { game, n }),
  coldReadAnswer: (body: {
    question_id: string
    session: string
    read: string
    self_report?: string
    seconds: number
  }) => post<ColdReadResult>('/api/game/answer', { game: 'coldread', ...body }),
  autopsyAnswer: (body: {
    question_id: string
    session: string
    mapping: Record<string, string>
    seconds: number
  }) => post<AutopsyResult>('/api/game/answer', { game: 'autopsy', ...body }),
  gameStats: () => get<GameStats>('/api/games/stats'),

  examList: () => get<{ exams: ExamSummary[] }>('/api/exams'),
  examNew: (body: { n: number; minutes: number; domain?: string }) =>
    post<ExamState>('/api/exam/new', body),
  examGet: (id: string) => get<ExamState>(`/api/exam/${encodeURIComponent(id)}`),
  examResult: (id: string) =>
    get<ExamResult>(`/api/exam/${encodeURIComponent(id)}/result`),
  examAnswer: (
    id: string, question_id: string, chosen: Letter | '', seconds: number,
    confidence: Confidence = '',
  ) =>
    post<ExamUpdateAck>('/api/exam/update', {
      id, action: 'answer', question_id, chosen, seconds, confidence,
    }),
  examFlag: (id: string, question_id: string) =>
    post<ExamUpdateAck>('/api/exam/update', { id, action: 'flag', question_id }),
  examPosition: (id: string, position: number) =>
    post<ExamUpdateAck>('/api/exam/update', { id, action: 'position', position }),
  examTick: (id: string, elapsed: number) =>
    post<ExamUpdateAck>('/api/exam/update', { id, action: 'tick', elapsed }),
  examSubmit: (id: string, elapsed: number) =>
    post<ExamResult>('/api/exam/submit', { id, elapsed }),

  calibration: () => get<Calibration>('/api/calibration'),
  settings: () => get<{ target_date: string }>('/api/settings'),
  saveSettings: (target_date: string) =>
    post<{ target_date: string }>('/api/settings', { target_date }),

  caseList: () => get<{ cases: CaseListEntry[] }>('/api/cases'),
  caseStart: (case_id: string) => post<CaseState>('/api/case/start', { case_id }),
  caseGet: (session: string) =>
    get<CaseState>(`/api/case/${encodeURIComponent(session)}`),
  caseChoose: (session: string, node: string, key: string, seconds: number) =>
    post<CaseChoice>('/api/case/choose', { session, node, key, seconds }),
  /** Only resolves once the run has finished — the server enforces that. */
  caseDebrief: (session: string) =>
    get<CaseDebrief>(`/api/case/${encodeURIComponent(session)}/debrief`),
}

export interface ExamUpdateAck {
  ok: boolean
  answered: number
  flagged: string[]
  elapsed: number
  remaining: number
}
