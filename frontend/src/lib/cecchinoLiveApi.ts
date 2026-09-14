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

export type LiveModules = {
  balance_classes?: Record<string, string | null> | null
  goal_intensity_classes?: Record<string, string | null> | null
  goal_intensity_final?: string | null
  eligibility?: string | null
  history_matches?: number | null
  patterns?: LivePatterns
}

export type LiveModelPrediction = {
  model: string
  status: 'open' | 'settled' | 'void' | 'preview' | 'error'
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

export async function getLiveFixture(todayFixtureId: number): Promise<LiveFixtureResponse> {
  return requestJson<LiveFixtureResponse>(`/api/cecchino-live/fixture/${todayFixtureId}`)
}

export async function getLiveObservation(scanDate: string): Promise<{ scan_date: string; items: LiveObservationItem[] }> {
  return requestJson(`/api/cecchino-live/observation?scan_date=${encodeURIComponent(scanDate)}`)
}
