/** API registro previsioni live (V2, V2.5) e osservazione pattern Master. */

import { requestJson } from './api'

export type LiveMarket = {
  probability: number | null
  quota_cecchino: number | null
  quota_book: number | null
  prob_book_fair?: number | null
  rating: number | null
  vantaggio_prob: number | null
  edge_pct: number | null
  buyability_score?: number | null
  buyability_class?: string | null
  signal_active?: boolean
}

export type LivePatternSignal = {
  id: number
  target_type: 'market' | 'synthetic'
  target_key: string
  threshold: number | null
  direction: number
  market_label: string
  conditions_text: string
  total_n: number
  win_rate_pct: number | null
  roi_pct: number | null
  avg_quota: number | null
  avg_deviation_pct: number | null
  quota_book: number | null
  /** Una condizione usa la quota del bookmaker (acquistabilità, distanza dal book, fascia di quota). */
  uses_book?: boolean
}

export type LivePatterns = {
  status: string
  master_build_id?: number
  active?: LivePatternSignal[]
  active_count?: number
  unverifiable_count?: number
  patterns_total?: number
  extra_stats?: {
    prior_matches: number | null
    prior_matches_with_stats: number | null
    delta_classes_available: number
  }
}

export type LiveIndexMarket = {
  probability: number
  base_rate: number
  score: number
  is_prediction: boolean
  quota: number | null
  min_quota: number | null
  playable: boolean
}

/** Indice di Acquistabilità V2.5 (orchestratore): legge i moduli, la quota serve solo alla fine. */
export type LivePurchasabilityIndex = {
  status: string
  error?: string
  source?: string
  module_version?: string
  trained_on?: string[]
  prediction_min_score?: number
  playable_min_quota?: number
  markets?: Record<string, LiveIndexMarket>
  predictions?: string[]
}

export type LiveBalancePillar = {
  title?: string | null
  index?: number | null
  raw_value?: number | null
  class_key?: string | null
  class_label?: string | null
  direction?: string | null
}

export type LiveGoalPillar = {
  title?: string | null
  score?: number | null
  raw_value?: number | null
  class_key?: string | null
  label?: string | null
}

export type V3IndexBlock = {
  value?: number | null
  class?: string | null
  percentile?: number | null
  favourite?: string | null
  gap_pp?: number | null
  prob?: number | null
  league_draw_rate?: number | null
  delta_pp?: number | null
  total?: number | null
  home?: number | null
  away?: number | null
  league_goals_avg?: number | null
  ratio?: number | null
  p_over_2_5?: number | null
}

export type V3Specialists = {
  forza?: { home: number | null; away: number | null }
  sot?: { home: number | null; away: number | null; volume_home: number | null; volume_away: number | null }
  shots?: { home: number | null; away: number | null; volume_home: number | null; volume_away: number | null }
  weights?: Record<string, number>
  form?: Record<string, number | null>
  calendar?: { rest_days_home: number | null; rest_days_away: number | null; final_phase: boolean }
}

export type V3History = {
  matches_current_season?: number
  matches_previous_season?: number
  matches_with_statistics?: number
  statistics_share?: number
  team_matches_with_statistics?: [number, number]
}

export type LiveModules = {
  engine_label?: string
  rho?: number | null
  ht_share?: number | null
  phase?: string | null
  played?: { home: number | null; away: number | null }
  evidence?: { home: number | null; away: number | null }
  specialists?: V3Specialists
  indices?: {
    equilibrio?: V3IndexBlock
    pareggio?: V3IndexBlock
    intensita_goal?: V3IndexBlock
    forma?: { home?: { gioco: number; risultati: number; matches: number | null } | null; away?: { gioco: number; risultati: number; matches: number | null } | null }
    calendario?: { rest_days_home: number | null; rest_days_away: number | null; rest_diff: number | null; final_phase: boolean }
  }
  history?: V3History
  params?: { source_run_id?: number | null; season?: string; engine_version?: string }
  balance_classes?: Record<string, string | null> | null
  goal_intensity_classes?: Record<string, string | null> | null
  goal_intensity_final?: string | null
  balance_pillars?: Record<string, LiveBalancePillar> | null
  goal_intensity_pillars?: Record<string, LiveGoalPillar> | null
  goal_intensity_final_detail?: { key?: string | null; label?: string | null; score?: number | null } | null
  expected_goals?: { home: number | null; away: number | null } | null
  eligibility?: string | null
  history_matches?: number | null
  patterns?: LivePatterns
  purchasability_index?: LivePurchasabilityIndex
}

export type LiveModelPrediction = {
  model: string
  status: 'open' | 'settled' | 'void' | 'preview' | 'error' | 'unavailable'
  reason?: string
  history?: V3History | null
  source: 'registro' | 'anteprima_non_registrata' | 'anteprima'
  eligible?: boolean
  engine_version?: string
  frozen_at?: string | null
  markets?: Record<string, LiveMarket>
  modules?: LiveModules | null
  result?: { score?: Record<string, number | null>; markets?: Record<string, { won: boolean | null; profit: number | null }> } | null
  error?: string
}

export type LiveFixtureResponse = {
  today_fixture_id: number
  models: Record<string, LiveModelPrediction>
}

export type LiveObservationItem = {
  today_fixture_id: number
  kickoff: string | null
  league_name: string | null
  home_team_name: string | null
  away_team_name: string | null
  model: string
  status: string
  pattern: LivePatternSignal
  result: { won: boolean | null; profit: number | null } | null
}

/** Pattern accesi sulla stessa partita raggruppati per mercato, linea e direzione. */
export type LivePatternGroup = {
  key: string
  target_type: 'market' | 'synthetic'
  target_key: string
  threshold: number | null
  direction: number
  market_label: string
  quota_book: number | null
  pattern_ids: number[]
  patterns_count: number
  max_total_n: number
  hist_win_rate_pct: number | null
  hist_roi_pct_best: number | null
  hist_deviation_pct: number | null
}

export type LiveObservationGroupItem = Omit<LiveObservationItem, 'pattern' | 'result'> & {
  group: LivePatternGroup
  result: { won: boolean | null; profit: number | null; actual?: number | null } | null
}

export type EngineFamilyMetrics = {
  fixtures: number
  brier: number | null
  favourite_hit_pct: number | null
}

export type EngineMetrics = Record<string, Record<string, EngineFamilyMetrics>>

export type ObservationGroupStats = {
  model: string
  key: string
  target_type: 'market' | 'synthetic'
  target_key: string
  threshold: number | null
  direction: number
  market_label: string
  signals: number
  won: number
  lost: number
  pending: number
  profit: number
  priced: number
  win_rate_pct: number | null
  roi_pct: number | null
  avg_quota: number | null
  avg_patterns: number | null
  hist_win_rate_pct: number | null
  hist_deviation_pct: number | null
}

export type ObservationPatternStats = {
  id: number
  model: string
  target_type: 'market' | 'synthetic'
  target_key: string
  market_label: string
  conditions_text: string
  total_n: number | null
  hist_win_rate_pct: number | null
  hist_roi_pct: number | null
  hist_deviation_pct: number | null
  signals: number
  won: number
  lost: number
  pending: number
  profit: number
  priced: number
  win_rate_pct: number | null
  roi_pct: number | null
}

export type ObservationDashboard = {
  date_from: string | null
  date_to: string | null
  models: string[]
  book_reference: string
  totals: {
    fixtures: number
    fixtures_settled: number
    common_fixtures: number
    predictions_by_model: Record<string, number>
    settled_by_model: Record<string, number>
    signals: number
    signals_closed: number
  }
  engines: EngineMetrics
  engines_base?: { models: string[]; fixtures: number; engines: EngineMetrics } | null
  engines_daily: {
    scan_date: string
    fixtures: number
    day: EngineMetrics
    cumulative_fixtures: number
    cumulative: EngineMetrics
  }[]
  pattern_groups: ObservationGroupStats[]
  patterns: ObservationPatternStats[]
  patterns_total: number
  concordance: { band: string; signals: number; won: number; lost: number; win_rate_pct: number | null }[]
  days: {
    scan_date: string
    fixtures: number
    fixtures_settled: number
    patterns_active: number
    groups_active: number
    groups_won: number
    groups_lost: number
    groups_pending: number
  }[]
}

export async function getLiveFixture(todayFixtureId: number): Promise<LiveFixtureResponse> {
  return requestJson<LiveFixtureResponse>(`/api/cecchino-live/fixture/${todayFixtureId}`)
}

export async function getLiveObservation(
  scanDate: string,
): Promise<{ scan_date: string; items: LiveObservationItem[]; groups: LiveObservationGroupItem[] }> {
  return requestJson(`/api/cecchino-live/observation?scan_date=${encodeURIComponent(scanDate)}`)
}

export async function getObservationDashboard(dateFrom: string | null, dateTo: string | null): Promise<ObservationDashboard> {
  const qs = new URLSearchParams()
  if (dateFrom) qs.set('date_from', dateFrom)
  if (dateTo) qs.set('date_to', dateTo)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return requestJson<ObservationDashboard>(`/api/cecchino-live/observation-dashboard${suffix}`)
}

/** Etichetta del gruppo: mercato con quota dal dizionario, senza quota dall'etichetta del pattern. */
export function groupLabel(g: { target_type: string; target_key: string; market_label: string }, marketLabels: Record<string, string>): string {
  return g.target_type === 'market' ? (marketLabels[g.target_key] ?? g.market_label) : g.market_label
}
