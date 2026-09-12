/** Client API Pattern Insights (Run V2) — dashboard esterna al Cecchino Lab.
 * Motore di scoperta su dati Run V2: vocabolario esteso (tiri/tiri in
 * porta/corner/cartellini/arbitro), 17 mercati (incluso primo tempo e
 * O/U 0.5/1.5/3.5) + bersagli sintetici senza quota storica. */

import { requestJson } from './api'

export type PatternInsightRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type PatternInsightRun = {
  id: number
  run_v2_run_id: number
  status: PatternInsightRunStatus
  requested_at: string | null
  started_at: string | null
  completed_at: string | null
  targets_total: number
  targets_processed: number
  current_target_label: string | null
  progress_pct: number | null
  summary: {
    targets_total?: number
    candidates_total?: number
    candidates_by_type?: { market?: number; synthetic?: number }
  } | null
  error: { message?: string } | null
  source_git_commit: string | null
}

export type PatternInsightTargetType = 'market' | 'synthetic'

export type PatternInsightSummaryTarget = {
  target_type: PatternInsightTargetType
  target_key: string
  target_label: string
  threshold: number | null
  count: number
  best_roi_pct: number | null
  best_abs_deviation_pct: number | null
}

export type PatternInsightSummary = {
  run: PatternInsightRun | null
  targets: PatternInsightSummaryTarget[]
  totals: { market: number; synthetic: number }
}

export type PatternInsightCandidate = {
  id: number
  insight_run_id: number
  target_type: PatternInsightTargetType
  target_key: string
  target_label: string
  threshold: number | null
  filters_json: Array<{ column: string; value: string }>
  filters_text: string
  filters_text_human: string
  refined_from_text: string | null
  n: number
  wins: number
  losses: number
  win_rate_pct: number | null
  roi_pct: number | null
  avg_quota: number | null
  baseline_win_rate_pct: number | null
  deviation_pct: number | null
}

export type PatternInsightCandidatesPage = {
  run: PatternInsightRun | null
  total: number
  items: PatternInsightCandidate[]
}

export async function getPatternInsightSummary(minN = 20): Promise<PatternInsightSummary> {
  return requestJson(`/api/admin/cecchino/research/run-v2-pattern-insight/summary?min_n=${minN}`)
}

export async function getPatternInsightCandidates(params: {
  targetType?: PatternInsightTargetType
  targetKey?: string
  threshold?: number
  minN?: number
  sort?: 'best' | 'roi_desc' | 'deviation_desc'
  limit?: number
  offset?: number
}): Promise<PatternInsightCandidatesPage> {
  const qs = new URLSearchParams()
  if (params.targetType) qs.set('target_type', params.targetType)
  if (params.targetKey) qs.set('target_key', params.targetKey)
  if (params.threshold != null) qs.set('threshold', String(params.threshold))
  qs.set('min_n', String(params.minN ?? 20))
  qs.set('sort', params.sort ?? 'best')
  qs.set('limit', String(params.limit ?? 100))
  qs.set('offset', String(params.offset ?? 0))
  return requestJson(`/api/admin/cecchino/research/run-v2-pattern-insight/candidates?${qs.toString()}`)
}

export async function startPatternInsightRun(runV2RunId: number): Promise<PatternInsightRun> {
  return requestJson('/api/admin/cecchino/research/run-v2-pattern-insight/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_v2_run_id: runV2RunId }),
  })
}

export async function getPatternInsightRun(runId: number): Promise<PatternInsightRun> {
  return requestJson(`/api/admin/cecchino/research/run-v2-pattern-insight/runs/${runId}`)
}

export async function cancelPatternInsightRun(runId: number): Promise<PatternInsightRun> {
  return requestJson(`/api/admin/cecchino/research/run-v2-pattern-insight/runs/${runId}/cancel`, {
    method: 'POST',
  })
}

export function isPatternInsightActive(run: PatternInsightRun): boolean {
  return run.status === 'pending' || run.status === 'running'
}

export function formatPct(v: number | null | undefined, decimals = 1): string {
  if (v == null || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(decimals)}%`
}
