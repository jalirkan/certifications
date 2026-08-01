/**
 * Types mirroring the Python API in drillkit/webapi.py.
 *
 * Two things are load-bearing here and deliberately encoded in the types:
 *
 * 1. `accuracy` is `number | null` everywhere. Null means "no data", not zero.
 *    Making it nullable forces every call site to handle the empty case rather
 *    than rendering a confident 0%.
 * 2. `Question` has no answer key. The server does not send one before the user
 *    commits, and there is no type in this file that would let a component
 *    render an answer it has not been given. The revealed shapes are separate.
 */

export type Letter = 'A' | 'B' | 'C' | 'D'

export interface Options {
  A: string
  B: string
  C: string
  D: string
}

/** Everything the browser sees before the user commits. No key, no rationale. */
export interface Question {
  id: string
  domain: string
  section: string
  topic: string
  tag: string
  difficulty: string
  stem: string
  /** Empty object in Cold Read: options are withheld until the read is committed. */
  options: Partial<Options>
  position: number
  total: number
}

export interface PrincipleRef {
  id: string
  name: string
  statement: string
  misapplication: string
  scope: string
}

/** Comes back only in the response to an answer. */
export interface Reveal {
  id: string
  answer: Letter
  chosen: Letter | null
  correct: boolean
  why_correct: string
  why_wrong: Partial<Record<Letter, string>>
  principle: PrincipleRef | null
}

// ---------------------------------------------------------------- bootstrap

export interface DomainTopic {
  section: string
  topic: string
}

export interface BootDomain {
  id: string
  name: string
  weight: number | null
  questions: number
  topics: DomainTopic[]
}

export interface ExamFormat {
  questions: number
  minutes: number
  score_scale: [number, number]
  passing_score: number
  format: string
  verified_on: string
}

export interface BootPrinciple {
  id: string
  name: string
  statement: string
  why: string
  misapplication: string
  scope: string
  questions: number
}

export interface Pair {
  id: string
  label: string
  domain: string
  terms: string[]
  discriminator: string
  trap: string
  questions: number
}

export interface Bootstrap {
  cert: string
  profile: string
  profiles: string[]
  questions: number
  domains: BootDomain[]
  exam: ExamFormat
  principles: BootPrinciple[]
  pairs: Pair[]
}

// ----------------------------------------------------------------- overview

/** A proportion that always travels with its Wilson bounds and denominator. */
export interface Interval {
  accuracy: number | null
  attempts: number
  low: number | null
  high: number | null
}

export interface DomainStat extends Interval {
  id: string
  name: string
  weight: number
  questions: number
}

export interface RuleStat extends Interval {
  id: string
  name: string
  misapplication: string
  scope: string
  seen: number
  total: number
}

export interface TopicStat extends Interval {
  label: string
  correct: number
}

export interface ExamSummary {
  id: string
  created: string
  submitted: boolean
  answered: number
  total: number
  elapsed: number
  duration: number
  flagged?: number
  shortfall?: Record<string, number>
}

export interface Overview {
  attempts: number
  correct: number
  accuracy: number | null
  coverage_seen: number
  coverage_total: number
  study_days: number
  last7: number | null
  last7_attempts: number
  weighted_accuracy: number | null
  games: number
  domains: DomainStat[]
  rules: RuleStat[]
  topics: TopicStat[]
  exams: ExamSummary[]
}

// -------------------------------------------------------------------- trend

export interface TrendDomainPoint {
  accuracy: number | null
  low: number | null
  high: number | null
  attempts: number
  correct: number
}

export interface TrendPoint {
  date: string
  attempts: number
  correct: number
  cum_accuracy: number | null
  cum_low: number | null
  cum_high: number | null
  cum_attempts: number
  cum_correct: number
  roll_accuracy: number | null
  roll_low: number | null
  roll_high: number | null
  roll_attempts: number
  roll_correct: number
  domains: Record<string, TrendDomainPoint>
}

export interface Trend {
  days: number
  window: number
  points: TrendPoint[]
  domains: { id: string; name: string; weight: number | null }[]
  total_attempts: number
}

// -------------------------------------------------------------------- drill

export type DrillMode =
  | 'smart' | 'due' | 'weakest' | 'random' | 'principle' | 'costumes'

/** Author-assigned bands, plus `ramp` which reorders rather than filters. */
export type Difficulty = '' | 'easy' | 'medium' | 'hard' | 'expert' | 'ramp'

export const DIFFICULTY_BANDS: Exclude<Difficulty, '' | 'ramp'>[] = [
  'easy', 'medium', 'hard', 'expert',
]

/**
 * What a difficulty filter would actually yield, fetched before the session
 * starts. Short and empty pools are the normal case here, not the edge case:
 * a fifth of topic-plus-difficulty combinations return nothing at all.
 */
export interface DrillAvailability {
  difficulty: Difficulty
  requested: number
  pool_total: number
  matching: number
  available: number
  counts: Record<string, number>
  due_suppressed: number
  short: boolean
  empty: boolean
  caveat: string
  message: string
}

export interface DrillStartParams {
  mode: DrillMode
  n?: number
  domain?: string
  section?: string
  topic?: string
  principle?: string
  difficulty?: Difficulty
  seed?: number
}

export interface DrillStart {
  session: string
  mode: DrillMode
  header: string | null
  difficulty: Difficulty
  availability: DrillAvailability
  /** 1 means the selected set was all one band, so there is no ramp today. */
  ramp_bands: number
  questions: Question[]
}

// -------------------------------------------------------------------- games

export type GameName = 'coldread' | 'autopsy'

export interface AskType {
  id: string
  label: string
  gloss: string
}

export interface AutopsyExplanation {
  label: 'X' | 'Y' | 'Z'
  text: string
}

/** Autopsy reveals the key by design; Cold Read withholds even the options. */
export interface GameQuestion extends Question {
  answer?: Letter
  distractors?: Letter[]
  explanations?: AutopsyExplanation[]
}

export interface GameStart {
  session: string
  game: GameName
  ask_types: AskType[]
  questions: GameQuestion[]
}

export interface ColdReadResult extends Reveal {
  expected: string
  read: string
  read_correct: boolean
  options: Options
}

export interface AutopsyResult {
  id: string
  correct: boolean
  matched: number
  total: number
  truth: Record<string, string>
  why_correct: string
  principle: PrincipleRef | null
}

export interface GameStats {
  total: number
  by_game: { game: string; n: number; ok: number; secs: number; accuracy: number | null }[]
  misreads: { expected: string; read: string; count: number }[]
  self_report: Record<string, number>
}

// --------------------------------------------------------------------- exam

export interface ExamState {
  id: string
  submitted: boolean
  duration: number
  elapsed: number
  remaining: number
  position: number
  answers: Record<string, Letter>
  /** Per-question confidence, kept until the exam is submitted. */
  confidence?: Record<string, Confidence>
  flagged: string[]
  blueprint: Record<string, number>
  shortfall: Record<string, number>
  questions: Question[]
}

export interface ExamDomainResult {
  domain: string
  name: string
  weight: number
  asked: number
  correct: number
  accuracy: number
  /** accuracy gap x exam weight - the most actionable number in the app. */
  cost: number
}

export interface MissedQuestion extends Question, Reveal {}

export interface ExamResult {
  id: string
  total: number
  correct: number
  unanswered: number
  raw: number
  /** An approximation of ISACA's undisclosed scaling. Never a prediction. */
  scaled: number
  passed: boolean
  elapsed: number
  duration: number
  pass_mark: number
  by_domain: ExamDomainResult[]
  slowest: { id: string; topic: string; seconds: number }[]
  guessed_right: { id: string; topic: string }[]
  missed: MissedQuestion[]
}

// -------------------------------------------------------------- calibration

/** "" means not recorded — every answer logged before capture existed. */
export type Confidence = '' | 'guess' | 'unsure' | 'confident'

export const CONFIDENCE_LEVELS: Exclude<Confidence, ''>[] = [
  'guess', 'unsure', 'confident',
]

export interface CalibrationCell {
  level: Exclude<Confidence, ''>
  attempts: number
  correct: number
  accuracy: number | null
  low: number | null
  high: number | null
  /** False when the sample is too small for the rate to mean anything. */
  enough: boolean
}

export interface CalibrationGap {
  gap: number | null
  confident_accuracy: number | null
  confident_attempts: number
  confident_low: number | null
  confident_high: number | null
  other_accuracy: number | null
  other_attempts: number
  overall_accuracy: number | null
  overall_attempts: number
  /** Interval on the difference itself. The confident cell's own interval is
   *  not the uncertainty of a gap between two rates. */
  gap_low: number | null
  gap_high: number | null
  /** True when the interval includes zero: no relationship established. */
  spans_zero: boolean | null
  enough: boolean
}

export interface CalibrationItem {
  question_id: string
  ts: string
  topic: string
  domain: string
  chosen: string
  answer: string
  confidence: Confidence
  mode: string
  seconds: number
  rule: string
  stem: string
}

export interface CalibrationBucket {
  key: string
  label: string
  attempts: number
  dangerous: number
  lucky: number
  confident_attempts: number
  confident_accuracy: number | null
  confident_low: number | null
  confident_high: number | null
  enough: boolean
  cells: CalibrationCell[]
}

export interface Projection {
  questions: number
  coverage_target: number
  covered: number
  attempts_remaining: number
  window_days: number
  recent_attempts: number
  active_days: number
  pace_per_day: number
  enough: boolean
  min_pace_attempts: number
  days_needed: number | null
  projected_date: string | null
  target: string | null
  days_to_target: number | null
  margin_days: number | null
  on_track: boolean | null
  today: string
}

export interface Calibration {
  attempts: number
  labelled: number
  unlabelled: number
  min_level: number
  curve: CalibrationCell[]
  gap: CalibrationGap
  dangerous: CalibrationItem[]
  lucky: CalibrationItem[]
  by_rule: CalibrationBucket[]
  by_topic: CalibrationBucket[]
  projection: Projection
}

// -------------------------------------------------------------------- cases

/**
 * Branching cases.
 *
 * The mid-run types below carry no `quality` and no `why` — the server does not
 * send them before the debrief, and there is no type here that would let a
 * component render which option is best. Same discipline as `Question`.
 */

export interface CaseHeader {
  id: string
  title: string
  domain: string
  section: string
  topics: string[]
  principles: string[]
  minutes: number
}

export interface CaseListEntry extends CaseHeader {
  nodes: number
  endings: number
  longest: number
  attempts: number
  verdicts: string[]
  last_played: string | null
  open_session: string | null
  open_decisions: number
}

/** Key and text only. Deliberately nothing else. */
export interface CaseOption {
  key: string
  text: string
}

export interface CaseNode {
  id: string
  situation: string
  prompt: string
  options: CaseOption[]
  position: number
  longest: number
}

/** What the learner already saw. Consequences are neutral by design. */
export interface CaseTrailEntry {
  node: string
  situation: string
  prompt: string
  chosen: string
  text: string
  consequence: string
}

export interface CaseState {
  session: string
  case: CaseHeader
  opening: string
  node: CaseNode | null
  trail: CaseTrailEntry[]
  finished: boolean
  decisions?: number
}

export interface CaseChoice {
  session: string
  consequence: string
  chosen: string
  decisions: number
  finished: boolean
  next: CaseNode | null
}

export type Quality = 'best' | 'defensible' | 'poor'
export type Verdict = 'strong' | 'acceptable' | 'weak' | 'failed'

/** Debrief only. This is the first payload that carries quality and why. */
export interface DebriefOption {
  key: string
  text: string
  quality: Quality
  why: string
  consequence: string
  chosen: boolean
  taint: string | null
  leads_to: string
  diverges: boolean
}

export interface DebriefStep {
  index: number
  node: string
  situation: string
  prompt: string
  chosen: string
  quality: Quality
  best: string
  seconds: number
  options: DebriefOption[]
}

export interface CaseEnding {
  id: string
  title: string
  verdict: Verdict | ''
  narrative: string
  why: string
}

/** Present only when a taint changed the outcome. */
export interface OverrideDetail {
  taint: string
  decision: number
  of: number
  decisions_before_end: number
  node: string
  prompt: string
  chosen: string
  text: string
  why: string
}

export interface CaseDebrief {
  session: string
  case: CaseHeader
  decisions: number
  counts: Record<Quality, number>
  taints: string[]
  ending: CaseEnding
  overridden: boolean
  override: OverrideDetail | null
  graph_ending: { id: string; title: string; verdict: string } | null
  walk: DebriefStep[]
  /** ending id -> label, for naming where an untaken branch would have gone. */
  endings_index: Record<string, { title: string; verdict: string }>
  principles: string[]
  seconds: number
  finished_at: string
}

// -------------------------------------------------------------------- items

export interface SuspectItem {
  id: string
  topic: string
  p: number | null
  attempts: number
  discrimination: number | null
  flags: string[]
}

export interface HardestItem {
  id: string
  topic: string
  p: number | null
  attempts: number
  low: number
  high: number
  seconds: number | null
}

export interface Items {
  total: number
  served: number
  never_served: number
  with_stats: number
  mean_p: number | null
  mean_discrimination: number | null
  spread: Record<string, number>
  flags: Record<string, number>
  suspect: SuspectItem[]
  hardest: HardestItem[]
}
