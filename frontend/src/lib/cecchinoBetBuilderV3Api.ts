import { requestJson } from './api'

export type BbV3PatternRelation = 'confermata' | 'in_contrasto' | 'altri_pattern' | 'senza_pattern'
export type BbV3Family = 'esito' | 'primo_tempo' | 'gol'

export type BbV3Prediction = {
  market_key: string
  family: BbV3Family
  score: number
  probability: number | null
  base_rate: number | null
  quota: number | null
  min_quota: number | null
  playable: boolean
  pattern: BbV3PatternRelation
  pattern_info: { patterns_count: number; hist_win_pct: number | null; hist_roi_pct: number | null } | null
  won: boolean | null
}

export type BbV3ModelBlock = {
  available: boolean
  status: string
  frozen_at: string | null
  predictions: BbV3Prediction[]
  patterns: {
    market_key: string
    patterns_count: number
    hist_win_pct: number | null
    hist_roi_pct: number | null
    quota: number | null
    won: boolean | null
  }[]
}

export type BbV3Combo = {
  market_key: string
  family: BbV3Family
  score: number
  score_v25: number
  score_v3: number
  quota: number | null
  min_quota: number | null
  playable: boolean
  pattern_v25: BbV3PatternRelation
  pattern_v3: BbV3PatternRelation
  won: boolean | null
}

export type BbV3Fixture = {
  today_fixture_id: number
  scan_date: string
  kickoff: string | null
  country: string | null
  league: string | null
  home: { name: string | null; logo: string | null }
  away: { name: string | null; logo: string | null }
  match_status: string
  score: { home: number; away: number } | null
}

export type BbV3FixtureItem = {
  fixture: BbV3Fixture
  models: Record<'V2.5' | 'V3', BbV3ModelBlock | null>
  combo: BbV3Combo[]
}

export type BbV3Response = {
  date_from: string
  date_to: string
  available_from: string
  thresholds: { index_min_score: number; playable_min_quota: number }
  fixtures: BbV3FixtureItem[]
}

export function fetchBetBuilderV3(params: { date_from: string; date_to: string }): Promise<BbV3Response> {
  const qs = new URLSearchParams(params).toString()
  return requestJson<BbV3Response>(`/api/cecchino/bet-builder/v3?${qs}`)
}
