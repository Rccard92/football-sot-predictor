/**
 * API client Preview Intensità Goal v5 — Fase 2A (research).
 */

import { adminGetJson, adminPostJson } from './api'

export type GoalIntensityV5PreviewRefreshRequest = {
  date_from?: string | null
  date_to?: string | null
  competition_id?: number | null
}

export type GoalIntensityV5PreviewBundleSummary = {
  bundle_id: number
  version: string
  candidate_indices_version?: string
  candidate_definition_hash?: string
  candidate_definition_hash_short?: string
  frozen_at?: string | null
  bundle_frozen_at?: string | null
  candidate_definition_frozen_at?: string | null
  prospective_window_started_at?: string | null
  prospective_start_mode?: string
  retrospective_exclusion_mode?: string
  retrospective_identity_count?: number
  first_prospective_scan_date?: string
  is_active?: boolean
  collected?: number
  prospective_matches_collected?: number
  completed?: number
  pending?: number
  locked?: number
  incomplete?: number
  error?: number
  minimum_prospective_matches?: number
  progress_to_minimum?: number
  protocol_status?: string
  primary_candidate?: string
  challenger_candidate?: string
  benchmark_candidate?: string
  diagnostic_candidate?: string
}

export type GoalIntensityV5PreviewSnapshotRow = {
  id: number
  today_fixture_id: number
  scan_date?: string | null
  kickoff?: string | null
  competition_id?: number | null
  competition_name?: string | null
  home_team_name?: string | null
  away_team_name?: string | null
  snapshot_status?: string
  preview_status?: string
  source_snapshot_at?: string | null
  history_sample_size?: number | null
  xg_status?: string | null
  GI_A?: number | null
  GI_B?: number | null
  MT1?: number | null
  GI_A_without_volatility?: number | null
  expected_goals_GI_A?: number | null
  p_ge2_GI_A?: number | null
  p_ge3_GI_A?: number | null
  p_btts_GI_A?: number | null
  total_goals_ft?: number | null
  result_attached?: boolean
}

export type GoalIntensityV5PreviewListResponse = {
  status: string
  version?: string
  bundle?: GoalIntensityV5PreviewBundleSummary
  total?: number
  limit?: number
  offset?: number
  items?: GoalIntensityV5PreviewSnapshotRow[]
  error?: string
}

export type GoalIntensityV5PreviewRefreshResponse = {
  status: string
  version?: string
  bundle_id?: number
  counters?: Record<string, number>
  monitoring_status?: string
  completed_prospective_matches?: number
  phase_2b_readiness?: Record<string, unknown>
  elapsed_ms?: number
  error?: string
}

export type GoalIntensityV5PreviewMonitoringResponse = Record<string, unknown> & {
  status: string
  completed_prospective_matches?: number
  minimum_prospective_matches?: number
  metrics_by_candidate?: Record<string, unknown>
  comparisons?: Record<string, unknown>
  phase_2b_readiness?: Record<string, unknown>
}

export type GoalIntensityV5PreviewExportKind =
  | 'summary'
  | 'snapshots'
  | 'completed-results'
  | 'candidate-monitoring'
  | 'calibration'
  | 'bundle-definition'

const PREVIEW_EXPORT_PATH: Record<GoalIntensityV5PreviewExportKind, string> = {
  summary: '/api/admin/cecchino/research/goal-intensity-v5/preview/export/summary',
  snapshots: '/api/admin/cecchino/research/goal-intensity-v5/preview/export/snapshots',
  'completed-results':
    '/api/admin/cecchino/research/goal-intensity-v5/preview/export/completed-results',
  'candidate-monitoring':
    '/api/admin/cecchino/research/goal-intensity-v5/preview/export/candidate-monitoring',
  calibration: '/api/admin/cecchino/research/goal-intensity-v5/preview/export/calibration',
  'bundle-definition':
    '/api/admin/cecchino/research/goal-intensity-v5/preview/export/bundle-definition',
}

export function fetchGoalIntensityV5Preview(params: {
  date_from?: string
  date_to?: string
  competition_id?: number | null
  status?: string
  limit?: number
  offset?: number
}): Promise<GoalIntensityV5PreviewListResponse> {
  const q = new URLSearchParams()
  if (params.date_from) q.set('date_from', params.date_from)
  if (params.date_to) q.set('date_to', params.date_to)
  if (params.competition_id != null) q.set('competition_id', String(params.competition_id))
  if (params.status) q.set('status', params.status)
  if (params.limit != null) q.set('limit', String(params.limit))
  if (params.offset != null) q.set('offset', String(params.offset))
  const qs = q.toString()
  return adminGetJson(
    `/api/admin/cecchino/research/goal-intensity-v5/preview${qs ? `?${qs}` : ''}`,
  )
}

export function refreshGoalIntensityV5Preview(
  body: GoalIntensityV5PreviewRefreshRequest,
): Promise<GoalIntensityV5PreviewRefreshResponse> {
  return adminPostJson('/api/admin/cecchino/research/goal-intensity-v5/preview/refresh', body)
}

export function fetchGoalIntensityV5PreviewMonitoring(): Promise<GoalIntensityV5PreviewMonitoringResponse> {
  return adminGetJson('/api/admin/cecchino/research/goal-intensity-v5/preview/monitoring')
}

export async function downloadGoalIntensityV5PreviewExport(
  kind: GoalIntensityV5PreviewExportKind,
): Promise<{ blob: Blob; filename: string }> {
  const base = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
  const path = PREVIEW_EXPORT_PATH[kind]
  const res = await fetch(`${base}${path}`)
  if (!res.ok) {
    throw new Error(`Export preview fallito (${res.status})`)
  }
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] ?? `cecchino_goal_intensity_v5_preview_${kind}.bin`
  const blob = await res.blob()
  return { blob, filename }
}
