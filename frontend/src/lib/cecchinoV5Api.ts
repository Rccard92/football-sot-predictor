/** Client di lettura Cecchino V5 (docs/v5/LIVE_REGOLE.md) e confronto dei motori (`/api/cecchino/engines/compare`). */

import { requestJson } from './api'

export type V5Status = 'consigliata' | 'osservazione'

export type EngineMeta = {
  engine: string
  label: string
  family: string
  v5_status?: V5Status
}

export type RoiStats = {
  plays: number
  won: number
  win_pct: number | null
  break_even_pct: number | null
  avg_quota: number | null
  profit: number
  roi_pct: number | null
  roi_low_pct: number | null
  roi_high_pct: number | null
}

export type EngineTotal = EngineMeta &
  RoiStats & {
    avg_clv_pct: number | null
    calibration: {
      plays_with_probability: number
      predicted_win_pct: number
      actual_win_pct: number
      gap_pct: number
      brier: number
    } | null
  }

export type EngineDayCell = { plays: number; won: number; profit: number; roi_pct: number | null }

export type EnginesCompare = {
  date_from: string
  date_to: string
  days: number
  engines: EngineMeta[]
  totals: EngineTotal[]
  daily: { day: string; engines: Record<string, EngineDayCell> }[]
  cumulative: Record<string, { day: string; profit: number }[]>
  errors: Record<string, string>
  v5_version: string
  computed_at: string
}

export type V5Combo = {
  scenario: string
  scenario_label: string
  label: string
  legs: { key: string; label: string }[]
  probability: number
  probability_independent: number
  fair_quota: number
  min_quota: number
  leg_quotes?: number[] | null
}

export type V5Play = {
  id: number
  specialist: string
  status: V5Status
  fixture_id: number
  league_code: string
  competition: string
  kickoff_at: string | null
  home_team: string
  away_team: string
  market_key: string
  label: string
  expected: number | null
  probability: number
  prob_prudent: number
  quota: number
  bookmaker: string
  taken_at: string | null
  closing_quota: number | null
  clv: number | null
  result: string | null
  profit_units: number | null
  score: string | null
  combo?: V5Combo | null
}

export type V5Day = {
  day: string
  version: string
  specialists: { key: string; label: string; status: V5Status; plays: V5Play[]; summary: RoiStats }[]
}

export function fetchEnginesCompare(days: number): Promise<EnginesCompare> {
  return requestJson<EnginesCompare>(`/api/cecchino/engines/compare?days=${days}`)
}

export function fetchV5Day(day?: string): Promise<V5Day> {
  return requestJson<V5Day>(`/api/cecchino/v5/plays${day ? `?date=${day}` : ''}`)
}

// --- Scheda V5 nel dettaglio partita di Cecchino Today -------------------------------

export type V5Candidate = {
  market_key: string
  label: string
  probability: number
  prob_prudent: number
  quota: number
  bookmaker: string | null
  score: number
}

export type V5StatLine = {
  side: 'total' | 'home' | 'away'
  line: number
  p_over: number
  p_under: number
  quota_over: number | null
  book_over: string | null
  quota_under: number | null
  book_under: string | null
}

export type V5ValoreMarket = {
  market_key: string
  label: string
  p_model: number
  p_calibrated: number | null
  p_prudent: number | null
  quota: number | null
  bookmaker: string | null
  in_band: boolean
}

export type V5SpecialistView = {
  key: string
  label: string
  status: V5Status
  expected: { home: number; away: number; total: number } | null
  reason: string | null
  lines?: V5StatLine[]
  markets?: V5ValoreMarket[]
  playable: V5Candidate[]
}

export type V5FixturePlay = {
  specialist: string
  status: V5Status
  label: string
  quota: number
  bookmaker: string | null
  probability: number
  prob_prudent: number
  expected: number | null
  taken_at: string | null
  closing_quota: number | null
  clv: number | null
  result: string | null
  profit_units: number | null
  combo?: V5Combo | null
}

export type V5FixtureView = {
  status: 'ok' | 'fuori_perimetro' | 'not_found'
  message?: string
  version?: string
  fixture?: {
    v4_fixture_id: number
    competition: string
    home_team: string
    away_team: string
    kickoff_at: string | null
    referee: string | null
    lambda_home: number | null
    lambda_away: number | null
  }
  odds_taken_at?: string | null
  rules?: { prudence: number; min_edge: number; stat_quota: [number, number]; valore_quota: [number, number] }
  specialists?: V5SpecialistView[]
  specialist_labels?: Record<string, string>
  combos?: V5Combo[]
  plays?: V5FixturePlay[]
}

export function fetchV5TodayFixture(todayFixtureId: number): Promise<V5FixtureView> {
  return requestJson<V5FixtureView>(`/api/cecchino/v5/today-fixture/${todayFixtureId}`)
}
