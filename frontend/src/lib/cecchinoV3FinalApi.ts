/** Client API Cecchino V3 — pattern (protocollo V2), movimento di mercato e test finale 2025/26. */

import { requestJson } from './api'
import type { PlaySummary } from './cecchinoV3EvaluatorApi'

const BASE = '/api/admin/cecchino/v3'

export type RateRow = {
  season: string
  tested: number
  confirmed: number
  expected: number
  confirmed_rate_pct: number | null
  expected_rate_pct: number | null
  lift: number | null
}

export type Tally = {
  discovered: number
  per_season: RateRow[]
  overall_lift: number | null
  persistence: RateRow
}

export type FrozenTest = {
  from_seasons: string[]
  target_season: string
  patterns: number
  bets: number
  profit: number
  roi_pct: number | null
  pooled_pattern_bets: number
  pooled_roi_pct: number | null
  by_market: Array<{ market_key: string; patterns: number; bets: number; profit: number; roi_pct: number | null }>
}

export type MoveRow = {
  family: string
  season: string
  n: number
  beta?: number
  beta_low?: number
  beta_high?: number
  mean_abs_move?: number
  mean_abs_distance?: number
}

export type V2Comparison = {
  insight_run_id: number
  discovered: number
  per_season: RateRow[]
  overall_lift: number | null
  persistence: RateRow | null
  frozen: {
    patterns: number
    pooled_pattern_bets: number
    pooled_roi_pct: number | null
    union_reference: { patterns: number; bets: number; roi_pct: number; source: string }
  } | null
}

export type PatternRunSummary = {
  rows: number
  patterns: Tally
  patterns_by_size: Array<Tally & { size: number }>
  patterns_by_market: Array<Tally & { market_key: string }>
  frozen: FrozenTest
  exam: { P1: boolean; P2: boolean; P3: boolean; passed: boolean }
  market_move: { table: MoveRow[]; exam: Array<{ family: string; passed: boolean }>; passed: boolean }
  opening_plays: {
    total: PlaySummary & { mean_odds_gain: number | null; roi_at_close: number | null }
    by_season: Array<PlaySummary & { season: string; mean_odds_gain: number | null; roi_at_close: number | null }>
  }
  v2: V2Comparison | null
}

export type SimpleRun<T> = {
  id: number
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  current_step: string | null
  completed_at: string | null
  summary: T | null
  error: { message?: string } | null
}

export type AccuracyRow = {
  season: string
  family: string
  n: number
  brier_v3?: number
  brier_v2?: number
  brier_book?: number
  v3_vs_v2_pct?: number
  v3_vs_book_pct?: number
  v2_vs_book_pct?: number
}

export type EvaluatorLockbox = {
  information: Array<{ group: string; season: string; n: number; ll_book?: number; ll_valutatore?: number; c?: number; c_low?: number; c_high?: number; gain_pct?: number }>
  information_exam: Array<{ family: string; I1: boolean; I2: boolean; passed: boolean }>
  VALUTATORE_PRINCIPALI: PlaySummary
  V3_PURA_PRINCIPALI: PlaySummary
}

export type FinalSummary = {
  integrity: {
    compared_probabilities: number
    reference_probabilities: number
    max_diff: number | null
    lockbox_matches: number
    passed: boolean
  }
  accuracy: AccuracyRow[]
  v3_patterns: { tally: Tally; always_confirmed: FrozenTest; frozen_22_24: FrozenTest }
  v2_patterns: {
    tally: RateRow
    always_confirmed: { patterns: number; pooled_pattern_bets: number; pooled_roi_pct: number | null }
  } | null
  evaluator_closing: EvaluatorLockbox
  evaluator_opening: EvaluatorLockbox
  market_move: { table: MoveRow[]; exam: Array<{ family: string; passed: boolean }>; passed: boolean }
  exam: { F0: boolean; F1: boolean; F1_available: boolean; F2: boolean; F3: boolean | null; passed: boolean }
}

export type PatternItem = {
  id: number
  market_key: string
  size: number
  conditions: Array<{ column: string; value: string }>
  discovery_n: number
  discovery_roi: number
  seasons: Record<string, { n: number; roi: number | null; verdict: string; null_p: number | null }>
  confirmed_all: boolean
  frozen: boolean
}

export async function getPatternRuns(): Promise<{ latest: SimpleRun<PatternRunSummary> | null; completed: SimpleRun<PatternRunSummary> | null }> {
  return requestJson(`${BASE}/pattern/runs/latest`)
}

export async function getFinalRuns(): Promise<{ latest: SimpleRun<FinalSummary> | null; completed: SimpleRun<FinalSummary> | null }> {
  return requestJson(`${BASE}/finale/runs/latest`)
}

export async function listPatterns(params: {
  market?: string
  only?: '' | 'confirmed_all' | 'frozen'
  limit: number
  offset: number
}): Promise<{ total: number; items: PatternItem[] }> {
  const qs = new URLSearchParams({ limit: String(params.limit), offset: String(params.offset) })
  if (params.market) qs.set('market_key', params.market)
  if (params.only) qs.set('only', params.only)
  return requestJson(`${BASE}/pattern/elenco?${qs.toString()}`)
}

export const CONDITION_LABELS: Record<string, string> = {
  prob_v3: 'Probabilita V3',
  v3_vs_book: 'V3 meno book',
  quota: 'Quota',
  forma: 'Forma casa − ospite',
  equilibrio: 'Equilibrio',
  pareggio: 'Pareggio',
  intensita_goal: 'Intensita goal',
  segno_agenti: 'Specialisti concordi',
  riposo: 'Riposo',
  fase: 'Fase',
  livello: 'Livello',
}
