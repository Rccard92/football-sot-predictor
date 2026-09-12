/** Client API Pattern Grid — ricerca esaustiva sequenziale a 4 stadi (job + polling + classifica). */

import { requestJson } from './api'

export type PatternGridRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type PatternGridRun = {
  id: number
  market_key: string
  competition: string | null
  run_ids: number[]
  status: PatternGridRunStatus
  requested_at: string | null
  started_at: string | null
  completed_at: string | null
  stages_total: number
  stages_processed: number
  progress_pct: number | null
  summary: {
    seasons?: string[]
    candidates_total?: number
    candidates_total_positive?: number
    verdict_counts?: Record<string, number>
  } | null
  error: { message?: string } | null
  source_git_commit: string | null
}

export type PatternGridStageResult = {
  n: number
  wins: number
  win_rate_pct: number | null
  roi_pct: number | null
  status: 'confirmed' | 'rejected' | 'insufficient_sample'
}

export type PatternGridVerdict =
  | 'stable'
  | 'confirmed_once'
  | 'weakening'
  | 'decaying'
  | 'rejected'
  | 'pending_first_oos'

export type PatternGridCandidate = {
  id: number
  grid_run_id: number
  market_key: string
  market_label: string
  competition: string | null
  filters_json: Array<{ column: string; value: string }>
  filters_text: string
  filters_text_human: string
  born_stage: number
  refined_from_text: string | null
  per_stage: Record<string, PatternGridStageResult>
  total_n: number | null
  total_wins: number | null
  total_losses: number | null
  total_win_rate_pct: number | null
  total_roi_pct: number | null
  total_avg_quota: number | null
  final_verdict: PatternGridVerdict
}

export type PatternGridLeaderboard = {
  runs: Record<string, PatternGridRun>
  candidates: PatternGridCandidate[]
}

export const PATTERN_GRID_MARKET_KEYS = [
  'HOME',
  'DRAW',
  'AWAY',
  'ONE_X',
  'X_TWO',
  'ONE_TWO',
  'OVER_2_5',
  'UNDER_2_5',
] as const

export function isPatternGridActive(run: PatternGridRun): boolean {
  return run.status === 'pending' || run.status === 'running'
}

export async function getPatternGridLeaderboard(): Promise<PatternGridLeaderboard> {
  return requestJson('/api/admin/cecchino/research/pattern-grid/leaderboard')
}

export async function startPatternGridRun(
  marketKey: string,
  runIds: number[],
  competition?: string | null,
): Promise<PatternGridRun> {
  return requestJson('/api/admin/cecchino/research/pattern-grid/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ market_key: marketKey, run_ids: runIds, competition: competition || null }),
  })
}

export async function getPatternGridRun(runId: number): Promise<PatternGridRun> {
  return requestJson(`/api/admin/cecchino/research/pattern-grid/runs/${runId}`)
}

export async function getPatternGridCandidates(runId: number): Promise<PatternGridCandidate[]> {
  return requestJson(`/api/admin/cecchino/research/pattern-grid/runs/${runId}/candidates`)
}

export async function cancelPatternGridRun(runId: number): Promise<PatternGridRun> {
  return requestJson(`/api/admin/cecchino/research/pattern-grid/runs/${runId}/cancel`, {
    method: 'POST',
  })
}

export function formatRoiPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(1)}%`
}

const VERDICT_LABELS: Record<PatternGridVerdict, string> = {
  stable: 'Stabile',
  confirmed_once: 'Confermato 1 volta',
  weakening: 'In indebolimento',
  decaying: 'In decadimento',
  rejected: 'Respinto',
  pending_first_oos: 'In attesa di 1ª verifica',
}

export function verdictLabel(v: PatternGridVerdict): string {
  return VERDICT_LABELS[v] ?? v
}

export function verdictBadgeClass(v: PatternGridVerdict): string {
  if (v === 'stable' || v === 'confirmed_once') return 'lab-badge-ok'
  if (v === 'weakening' || v === 'pending_first_oos') return 'lab-badge-warn'
  return 'lab-badge-err'
}
