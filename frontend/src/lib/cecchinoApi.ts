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

export type CecchinoLeakageCheck = {
  status: string
  target_kickoff?: string | null
  max_source_fixture_date?: string | null
  checked_at?: string | null
}

export type CecchinoContextSnapshot = {
  key: string
  label?: string
  wdl: CecchinoWDL
  sample_count: number
  target_sample: number | null
  status?: string
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
  leakage_check: CecchinoLeakageCheck | string
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

export type CecchinoReliability = {
  sample?: number | null
  index?: number | null
  status?: string | null
  level?: string | null
}

export type CecchinoSignalRow = {
  key: string
  label: string
  signals: Record<string, string>
}

export type CecchinoSignalsMatrix = {
  status: string
  source?: string
  excel_mapping?: Record<string, string>
  inputs?: {
    q1?: number | null
    qx?: number | null
    q2?: number | null
    avg_q?: number | null
    diff_1_2?: number | null
  }
  rows?: CecchinoSignalRow[]
  reliability?: CecchinoReliability
  warnings?: string[]
}

export type CecchinoKpiRow = {
  market_key: string
  label: string
  statistica?: string | number | null
  cecchino?: string | number | null
  book?: string | number | null
  bookmakers?: Record<string, number | null>
  book_average?: number | null
  media?: number | null
  edge?: number | null
  edge_pct?: number | null
  status?: string
  warnings?: string[]
}

export type CecchinoKpiPanel = {
  version: string
  bookmakers_used?: Array<{ name: string; provider_bookmaker_id: number; status: string }>
  bookmaker_status?: string
  rows: CecchinoKpiRow[]
  delta_force_legend?: Array<{ range: string; label: string }>
  warnings?: string[]
}

export type CecchinoOutput = {
  picchetti: Record<string, CecchinoPicchetto>
  final: CecchinoFinalOdds
  signals_matrix: CecchinoSignalsMatrix
  reliability_index: CecchinoReliability | CecchinoPlaceholderSection
  bookmaker_comparison: CecchinoPlaceholderSection & { kpi_panel?: CecchinoKpiPanel }
  kpi_panel?: CecchinoKpiPanel
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
  kpi_panel?: CecchinoKpiPanel
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

export async function adminSyncCecchinoBookmakerOdds(
  competitionId: number,
  body?: { fixture_id?: number; bookmaker_ids?: number[]; markets?: string[] },
  opts?: AdminRequestOpts,
): Promise<unknown> {
  return adminPostJson<unknown>(
    `/api/admin/competitions/${competitionId}/cecchino/bookmakers/sync-next-round`,
    body ?? {},
    opts,
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
