/**
 * Client API Cecchino — modulo separato dal client SOT in api.ts.
 */

import { adminPostJson, requestJson, type AdminRequestOpts } from './api'

export type CecchinoWDL = { wins: number; draws: number; losses: number }

export type CecchinoOutcome = {
  prob: number | null
  prob_pct: number | null
  quota: number | null
  mathematical_odds?: number | null
}

export type CecchinoContextSnapshot = {
  key: string
  wdl: CecchinoWDL
  sample_count: number
  target_sample: number | null
  fixture_ids?: number[]
}

export type CecchinoDataQuality = {
  sample_home_context: number
  sample_away_context: number
  sample_home_total: number
  sample_away_total: number
  sample_home_recent_context: number
  sample_away_recent_context: number
  sample_home_recent_total: number
  sample_away_recent_total: number
  leakage_check: 'passed' | 'failed' | 'not_applicable' | string
  warnings: string[]
  fixture_ids_used?: Record<string, number[]>
}

export type CecchinoPicchetto = {
  key: string
  label: string
  input_records?: { home: CecchinoWDL; away: CecchinoWDL }
  home_context: CecchinoWDL
  away_context: CecchinoWDL
  sample_home?: number | null
  sample_away?: number | null
  target_sample_home?: number | null
  target_sample_away?: number | null
  total_matches: number
  outcome_1: CecchinoOutcome
  outcome_x: CecchinoOutcome
  outcome_2: CecchinoOutcome
  status: string
  warnings: string[]
}

export type CecchinoFinalOdds = {
  quota_1: number | null
  quota_x: number | null
  quota_2: number | null
  prob_1: number | null
  prob_x: number | null
  prob_2: number | null
  prob_1_pct: number | null
  prob_x_pct: number | null
  prob_2_pct: number | null
  status: string
  warnings: string[]
  weights: Record<string, number>
}

export type CecchinoPlaceholderSection = { status: string }

export type CecchinoOutput = {
  picchetti: Record<string, CecchinoPicchetto>
  final: CecchinoFinalOdds
  signals_matrix: CecchinoPlaceholderSection
  reliability_index: CecchinoPlaceholderSection
  bookmaker_comparison: CecchinoPlaceholderSection
  status: string
  warnings: string[]
  data_quality?: CecchinoDataQuality
}

export type CecchinoTeamBrief = {
  id: number
  name: string
  logo_url: string | null
}

export type CecchinoFixtureBrief = {
  fixture_id: number
  kickoff_at: string | null
  status: string
  round: string | null
  home_team: CecchinoTeamBrief
  away_team: CecchinoTeamBrief
}

export type CecchinoUpcomingFixtureRow = {
  fixture: CecchinoFixtureBrief
  calculation_status: string | null
  warnings: string[]
  data_quality?: {
    leakage_check?: string | null
    sample_home_total?: number | null
    sample_away_total?: number | null
  }
  final_quota_1: number | null
  final_quota_x: number | null
  final_quota_2: number | null
  final_prob_1_pct: number | null
  final_prob_x_pct: number | null
  final_prob_2_pct: number | null
}

export type CecchinoUpcomingResponse = {
  status: string
  cecchino_version: string
  competition_id: number
  round_label: string | null
  fixtures_count: number
  fixtures: CecchinoUpcomingFixtureRow[]
}

export type CecchinoFixtureDetailResponse = {
  status: string
  cecchino_version: string
  competition_id: number
  fixture: CecchinoFixtureBrief
  calculation_status: string
  input_snapshot: Record<string, CecchinoContextSnapshot | unknown>
  data_quality?: CecchinoDataQuality
  output?: CecchinoOutput
  warnings: string[]
  stored?: boolean
  updated_at?: string | null
  code?: string
  message?: string
}

export async function getCecchinoUpcomingForCompetition(
  competitionId: number,
  opts?: { limit?: number },
): Promise<CecchinoUpcomingResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  const q = p.toString()
  return requestJson<CecchinoUpcomingResponse>(
    `/api/competitions/${competitionId}/cecchino/upcoming${q ? `?${q}` : ''}`,
  )
}

export async function getCecchinoFixtureDetail(
  competitionId: number,
  fixtureId: number,
  opts?: { recalculate?: boolean },
): Promise<CecchinoFixtureDetailResponse> {
  const p = new URLSearchParams()
  if (opts?.recalculate) p.set('recalculate', 'true')
  const q = p.toString()
  return requestJson<CecchinoFixtureDetailResponse>(
    `/api/competitions/${competitionId}/cecchino/fixture/${fixtureId}${q ? `?${q}` : ''}`,
  )
}

export async function adminRecalculateCecchino(
  competitionId: number,
  body?: { fixture_id?: number; limit?: number },
  opts?: AdminRequestOpts,
): Promise<unknown> {
  return adminPostJson<unknown>(
    `/api/admin/competitions/${competitionId}/cecchino/recalculate`,
    body ?? {},
    opts,
  )
}
