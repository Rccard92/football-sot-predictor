/** Client API Cecchino V3 — Fase 1 (specialista Forza). */

import { requestJson } from './api'

const BASE = '/api/admin/cecchino/v3'

export type V3RunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type V3Metric = {
  n: number
  brier_v3: number | null
  brier_v2?: number | null
  brier_prev?: number | null
  brier_book: number | null
  log_loss_v3: number | null
  log_loss_v2?: number | null
  log_loss_book: number | null
  v3_vs_v2_pct?: number
  v3_vs_prev_pct?: number
  v3_vs_book_pct?: number
}

export type V3Family = 'FT_1X2' | 'DOUBLE_CHANCE' | 'FT_OVER_UNDER' | 'HT_1X2'

export type V3Evaluation = {
  warmup_season: string
  judge_seasons: string[]
  baseline_run_id?: number | null
  comparison_set: string
  exam: {
    passed: boolean
    reference?: 'v2' | 'prev'
    tolerance_pct?: number | null
    rules: string[]
    accuracy_vs_v2: Array<{
      family: V3Family
      passed: boolean
      mean_change_pct?: number | null
      seasons: Array<{
        season_label: string
        passed: boolean
        brier_v3: number | null
        brier_v2: number | null
        brier_reference?: number | null
        change_pct?: number | null
        brier_book: number | null
      }>
    }>
    calibration: Array<{
      family: V3Family
      calibration_error_pct: number | null
      max_allowed_pct: number
      passed: boolean
    }>
  }
  by_season: Array<V3Metric & { season_label: string; family: V3Family }>
  by_tier: Array<V3Metric & { season_label: string; family: V3Family; tier: 'top' | 'lower' }>
  by_phase: Array<V3Metric & { season_label: string; family: V3Family; phase: 'mid' | 'final' }>
  by_competition: Array<V3Metric & { competition_name: string; tier: 'top' | 'lower' }>
  v3_all_eligible: Array<V3Metric & { season_label: string; family: V3Family }>
  coverage: Array<{ season_label: string; v3_eligible_matches: number; common_matches: number }>
  calibration: Array<{
    family: V3Family
    bin: number
    n: number
    avg_probability_v3: number | null
    won_rate: number | null
    avg_probability_v2: number | null
    avg_probability_book: number | null
  }>
  calibration_error: Record<string, { v3_pct: number | null }>
}

export type V3Weights = {
  intercept: number
  forza: number
  sot: number
  shots: number
  form_goals?: number
  form_shots?: number
  rest_attack?: number
  rest_defence?: number
  final_phase?: number
  fouls_attack?: number
  fouls_defence?: number
  cards_defence?: number
  referee_goals?: number
}

export type V3Run = {
  id: number
  engine_version: string
  phase?: number
  status: V3RunStatus
  requested_at: string | null
  started_at: string | null
  completed_at: string | null
  progress_pct: number | null
  current_step: string | null
  config: {
    warmup_season: string
    judge_seasons: string[]
    lockbox_season: string
    min_matches_played: number
    final_phase_matches: number
    hyper_grid: Array<{ xi: number; sigma: number }>
  } | null
  summary: {
    seasons: Record<string, { matches: number; eligible: number; early: number; mid: number; final: number }>
    chosen_hyper: Record<string, { xi: number; sigma: number }>
    hyper_table: Record<string, { xi: number; sigma: number; log_loss_1x2: Record<string, number> }>
    written: { matches: number; markets: number }
    elapsed_seconds: number
    evaluation: V3Evaluation
    orchestrator_weights?: Record<string, V3Weights>
    base_orchestrator_weights?: Record<string, V3Weights>
    game_chosen_hyper?: Record<string, Record<string, { xi: number; sigma: number }>>
  } | null
  error: { message?: string } | null
}

export async function getLatestV3Runs(): Promise<{ latest: V3Run | null; completed: V3Run | null }> {
  return requestJson(`${BASE}/runs/latest`)
}

export async function startV3Run(phase = 2): Promise<V3Run> {
  return requestJson(`${BASE}/runs?phase=${phase}`, { method: 'POST' })
}

export type V3RunListItem = {
  id: number
  phase: number
  engine_version: string
  completed_at: string | null
  exam_passed: boolean | null
  user_decision?: { accepted: boolean; note: string; decided_at: string } | null
  reference_model?: boolean
}

export async function listV3Runs(): Promise<{ items: V3RunListItem[] }> {
  return requestJson(`${BASE}/runs`)
}

export async function getV3Run(runId: number): Promise<V3Run> {
  return requestJson(`${BASE}/runs/${runId}`)
}

export async function cancelV3Run(runId: number): Promise<V3Run> {
  return requestJson(`${BASE}/runs/${runId}/cancel`, { method: 'POST' })
}

export function isV3RunActive(run: V3Run | null | undefined): boolean {
  return run?.status === 'pending' || run?.status === 'running'
}

export const FAMILY_LABELS: Record<V3Family, string> = {
  FT_1X2: '1X2 finale',
  DOUBLE_CHANCE: 'Doppia chance',
  FT_OVER_UNDER: 'Over/Under',
  HT_1X2: '1X2 primo tempo',
}
