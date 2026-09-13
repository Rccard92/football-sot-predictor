/** Client API Cecchino V3 — valutatore di mercato (Passo 3). */

import { requestJson } from './api'

const BASE = '/api/admin/cecchino/v3/valutatore'

export type StrategyCode = 'VALUTATORE_PRINCIPALI' | 'V3_PURA_PRINCIPALI' | 'VALUTATORE_TUTTI'

export type PlaySummary = {
  n: number
  won?: number
  hit_rate?: number
  mean_probability?: number
  mean_book_probability?: number
  mean_odds?: number
  profit?: number
  roi?: number
  roi_se?: number | null
  roi_low?: number | null
  roi_high?: number | null
}

export type GroupedSummary = PlaySummary & { key: string }

export type StrategyReport = {
  total: PlaySummary
  by_season: GroupedSummary[]
  by_family: GroupedSummary[]
  by_market: GroupedSummary[]
  by_tier: GroupedSummary[]
  by_competition: GroupedSummary[]
  by_odds_band: GroupedSummary[]
  by_phase: GroupedSummary[]
  days_with_plays: number
  plays_per_day: number
}

export type InformationRow = {
  group: string
  season: string
  n: number
  ll_book?: number
  ll_v3?: number
  ll_valutatore?: number
  gain_pct?: number
  c?: number
  c_low?: number
  c_high?: number
  b?: number
}

export type EvaluatorSummary = {
  rows: number
  matches: number
  information: InformationRow[]
  information_exam: Array<{ family: string; I1: boolean; I2: boolean; passed: boolean }>
  information_passed: boolean
  combination_models: Array<{ season: string; market_key: string; n: number; a: number; b: number; c: number; c_low: number; c_high: number }>
  final_phase_rules: Array<{ season: string; family: string; excluded: boolean; n: number; gain: number | null }>
  strategies: Record<StrategyCode, StrategyReport>
  playability_exam: {
    G1: boolean
    G2: boolean
    G3: boolean
    passed: boolean
    by_season: Array<PlaySummary & { season: string }>
    total: PlaySummary
  }
  edge_grid: Array<{ min_edge: number; total: PlaySummary; by_season: Array<PlaySummary & { season: string }> }>
}

export type EvaluatorRun = {
  id: number
  source_run_id: number
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  current_step: string | null
  completed_at: string | null
  summary: EvaluatorSummary | null
  error: { message?: string } | null
}

export type EvaluatorPlay = {
  lab_match_id: number
  match_date: string
  season_label: string
  competition: string
  home_team: string
  away_team: string
  phase: string
  market_key: string
  odds: number
  p_v3: number
  p_book: number
  p_eval: number | null
  edge: number
  won: boolean
  profit: number
}

export async function getEvaluatorRuns(): Promise<{ latest: EvaluatorRun | null; completed: EvaluatorRun | null }> {
  return requestJson(`${BASE}/runs/latest`)
}

export async function startEvaluatorRun(): Promise<EvaluatorRun> {
  return requestJson(`${BASE}/runs`, { method: 'POST' })
}

export async function listPlays(params: {
  strategy: StrategyCode
  season?: string
  competition?: string
  limit: number
  offset: number
}): Promise<{ total: number; items: EvaluatorPlay[]; competitions: string[] }> {
  const qs = new URLSearchParams({ strategy: params.strategy, limit: String(params.limit), offset: String(params.offset) })
  if (params.season) qs.set('season_label', params.season)
  if (params.competition) qs.set('competition', params.competition)
  return requestJson(`${BASE}/giocate?${qs.toString()}`)
}

export const STRATEGY_LABELS: Record<StrategyCode, string> = {
  VALUTATORE_PRINCIPALI: 'Valutatore · mercati con quota di chiusura',
  V3_PURA_PRINCIPALI: 'V3 pura (senza correzione) · stessi mercati',
  VALUTATORE_TUTTI: 'Valutatore · tutti i 17 mercati',
}

export const INFORMATION_GROUP_LABELS: Record<string, string> = {
  FT_1X2: '1X2 finale',
  OU_2_5: 'Over/Under 2.5',
  DOPPIA_CHANCE: 'Doppia chance',
  OU_0_5: 'Over/Under 0.5',
  OU_1_5: 'Over/Under 1.5',
  OU_3_5: 'Over/Under 3.5',
  HT_1X2: '1X2 primo tempo',
}

export const FAMILY_LABELS: Record<string, string> = {
  FT_1X2: '1X2 finale',
  DOUBLE_CHANCE: 'Doppia chance',
  FT_OVER_UNDER: 'Over/Under',
  HT_1X2: '1X2 primo tempo',
}
