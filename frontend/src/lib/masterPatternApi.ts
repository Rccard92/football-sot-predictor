/** Client API Master Pattern: pattern vincenti 4/4 di V2, V2.5 e V3. */

import { requestJson } from './api'

const BASE = '/api/admin/cecchino/master-pattern'

export type ModelCode = 'V2' | 'V2.5' | 'V3'
export type TargetType = 'market' | 'synthetic'

export type TallyBlock = {
  patterns: number
  tested_all_seasons: number
  winners: number
  expected_by_chance: number
  lift: number | null
}

export type MasterBuild = {
  id: number
  model: ModelCode
  status: 'pending' | 'running' | 'completed' | 'failed'
  requested_at: string | null
  completed_at: string | null
  current_step: string | null
  summary: { tally: Record<TargetType, TallyBlock>; winners: number; source: Record<string, unknown> } | null
  error: { message?: string } | null
}

export type Overview = {
  models: Array<{ model: ModelCode; available: boolean; latest: MasterBuild | null; completed: MasterBuild | null }>
  rules: { discovery_season: string; verify_seasons: string[]; min_sample: number; synthetic_confirm_deviation_pct: number }
}

export type SeasonStats = {
  n: number
  wins: number
  losses?: number
  win_rate_pct: number | null
  roi_pct?: number | null
  profit_units?: number | null
  avg_quota?: number | null
  baseline_win_rate_pct?: number | null
  deviation_pct?: number | null
  verdict: string | null
}

export type MasterPattern = {
  id: number
  model: ModelCode
  engine_version: string
  target_type: TargetType
  target_key: string
  target_label: string
  threshold: number | null
  direction: number
  market_label: string
  conditions: Array<{ column: string; value: string; label?: string }>
  conditions_text: string
  seasons: Record<string, SeasonStats>
  total_n: number
  total_wins: number
  total_losses: number
  win_rate_pct: number | null
  profit_units: number | null
  roi_pct: number | null
  avg_quota: number | null
  avg_deviation_pct: number | null
}

export type DetailSeason = {
  season_label: string
  role: 'discovery' | 'validation'
  verdict: string | null
  overall: SeasonStats
  by_competition: Array<SeasonStats & { competition: string }>
  matches: Array<{
    season_label: string
    lab_match_id: number
    match_date: string
    competition: string
    home_team: string
    away_team: string
    won: boolean | null
    quota: number | null
    profit: number | null
    actual_value: number | null
  }>
  matches_total: number
}

export async function getOverview(): Promise<Overview> {
  return requestJson(`${BASE}/overview`)
}

export async function startBuild(model: ModelCode): Promise<MasterBuild> {
  return requestJson(`${BASE}/builds?model=${encodeURIComponent(model)}`, { method: 'POST' })
}

export async function listMasterPatterns(params: {
  model: ModelCode
  targetType: TargetType
  market?: string
  minMatches?: number
  minQuota?: number
  maxQuota?: number
  sort?: string
  limit: number
  offset: number
}): Promise<{ build: MasterBuild | null; total: number; items: MasterPattern[]; markets: Array<{ key: string; count: number }> }> {
  const qs = new URLSearchParams({
    model: params.model,
    target_type: params.targetType,
    limit: String(params.limit),
    offset: String(params.offset),
  })
  if (params.market) qs.set('market', params.market)
  if (params.minMatches) qs.set('min_matches', String(params.minMatches))
  if (params.minQuota != null) qs.set('min_quota', String(params.minQuota))
  if (params.maxQuota != null) qs.set('max_quota', String(params.maxQuota))
  if (params.sort) qs.set('sort', params.sort)
  return requestJson(`${BASE}/patterns?${qs.toString()}`)
}

export async function getMasterPatternDetail(id: number): Promise<{ pattern: MasterPattern; seasons: DetailSeason[] }> {
  return requestJson(`${BASE}/patterns/${id}`)
}

export const MARKET_LABELS: Record<string, string> = {
  HOME: '1',
  DRAW: 'X',
  AWAY: '2',
  ONE_X: '1X',
  X_TWO: 'X2',
  ONE_TWO: '12',
  OVER_0_5: 'Over 0.5',
  UNDER_0_5: 'Under 0.5',
  OVER_1_5: 'Over 1.5',
  UNDER_1_5: 'Under 1.5',
  OVER_2_5: 'Over 2.5',
  UNDER_2_5: 'Under 2.5',
  OVER_3_5: 'Over 3.5',
  UNDER_3_5: 'Under 3.5',
  HOME_PT: '1 primo tempo',
  DRAW_PT: 'X primo tempo',
  AWAY_PT: '2 primo tempo',
}

export const SEASONS = ['2021/2022', '2022/2023', '2023/2024', '2024/2025', '2025/2026']
