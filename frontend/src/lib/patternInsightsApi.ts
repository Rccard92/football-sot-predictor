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
  oos?: OosStats | null
}

export type PatternInsightCandidatesPage = {
  run: PatternInsightRun | null
  validation?: { id: number; season_label: string | null } | null
  total: number
  items: PatternInsightCandidate[]
}

export type MarketStat = {
  target_key: string
  target_label: string
  pattern_count: number
  best_roi_pct: number | null
  median_roi_pct: number | null
  avg_n: number | null
  max_n: number | null
  avg_quota: number | null
}

export type FactorStat = {
  column_key: string
  label: string
  uses: number
  avg_roi_pct: number | null
}

export type ComplexityStat = {
  atoms: number
  pattern_count: number
  avg_roi_pct: number | null
  avg_n: number | null
  avg_abs_deviation_pct: number | null
}

export type QualityPoint = {
  n: number
  roi_pct: number | null
  avg_quota: number | null
  target_label: string
}

export type SyntheticDirection = {
  target_key: string
  target_label: string
  threshold: number | null
  pattern_count: number
  best_up_pct: number | null
  best_down_pct: number | null
  baseline_pct: number | null
}

export type SampleBucket = {
  bucket: string
  pattern_count: number
  avg_roi_pct: number | null
}

export type SourceCoverage = {
  season_label?: string
  matches?: number
  date_range?: { start?: string; end?: string }
  elapsed_seconds?: number
  avg_ms_per_match?: number
  market_rows_written?: number
  leakage_ok?: boolean
  leakage_violations?: number
  matches_audited?: number
  referee_coverage_pct?: number
  quote_policy_version?: string
  competitions?: Array<{ competition: string; matches: number; eligible_core: number }>
  market_coverage?: Array<{
    market_key: string
    rows: number
    rows_with_quote: number
    quote_coverage_pct: number
  }>
}

export type PatternInsightAnalytics = {
  run: PatternInsightRun | null
  min_n?: number
  by_market?: MarketStat[]
  factor_frequency?: FactorStat[]
  by_complexity?: ComplexityStat[]
  quality_scatter?: QualityPoint[]
  synthetic_directions?: SyntheticDirection[]
  sample_buckets?: SampleBucket[]
  source_coverage?: SourceCoverage
}

export type ValidationRate = {
  total: number
  tested: number
  confirmed: number
  attenuated: number
  rejected: number
  insufficient: number
  confirmed_rate_pct: number | null
  expected_rate_pct: number | null
  lift: number | null
}

export type ValidationAnalytics = {
  validation: {
    id: number
    season_label: string | null
    completed_at: string | null
    summary: {
      parity_checked?: number
      parity_mismatches?: number
    } | null
  } | null
  min_n?: number
  headline?: Partial<Record<PatternInsightTargetType, ValidationRate>>
  by_bucket?: Array<ValidationRate & { bucket: string; target_type: PatternInsightTargetType }>
  by_complexity?: Array<ValidationRate & { atoms: number; target_type: PatternInsightTargetType }>
  by_target?: Array<
    ValidationRate & {
      target_type: PatternInsightTargetType
      target_key: string
      target_label: string
      disc_avg_roi_pct: number | null
      oos_avg_roi_pct: number | null
    }
  >
  shrinkage?: Array<{
    bucket: string
    disc_avg_roi_pct: number | null
    oos_avg_roi_pct: number | null
    patterns: number
  }>
  scatter?: Array<{
    disc_roi_pct: number | null
    oos_roi_pct: number | null
    n: number
    verdict: string
  }>
}

export async function getValidationAnalytics(minN = 20): Promise<ValidationAnalytics> {
  return requestJson(
    `/api/admin/cecchino/research/run-v2-pattern-insight/validation-analytics?min_n=${minN}`,
  )
}

export type OosStats = {
  n: number
  wins: number
  losses: number
  win_rate_pct: number | null
  roi_pct: number | null
  profit_units: number | null
  avg_quota: number | null
  baseline_win_rate_pct: number | null
  deviation_pct: number | null
  verdict: 'confirmed' | 'attenuated' | 'rejected' | 'insufficient_sample'
  null_confirm_prob: number | null
}

export const VERDICT_LABELS: Record<OosStats['verdict'], string> = {
  confirmed: 'Confermato',
  attenuated: 'Attenuato',
  rejected: 'Respinto',
  insufficient_sample: 'Campione insuff.',
}

export type LeagueBreakdown = {
  competition: string
  n: number
  wins: number
  losses: number
  win_rate_pct: number | null
  roi_pct: number | null
  profit_units: number | null
  avg_quota: number | null
  deviation_pct: number | null
  enough_sample: boolean
}

export type TriggeringMatch = {
  lab_match_id: number
  kickoff_at: string | null
  competition: string
  home_team: string | null
  away_team: string | null
  won: boolean | null
  quota_book: number | null
  profit_1u: number | null
  actual_value: number | null
}

export type PatternDetail = {
  candidate: {
    id: number
    target_type: PatternInsightTargetType
    target_key: string
    target_label: string
    threshold: number | null
    filters_text_human: string
    refined_from_text: string | null
    baseline_win_rate_pct: number | null
  }
  overall: {
    n: number
    wins: number
    losses: number
    win_rate_pct: number | null
    roi_pct: number | null
    profit_units: number | null
    avg_quota: number | null
  }
  by_competition: LeagueBreakdown[]
  concentration: {
    leagues_total: number
    leagues_with_sample: number
    leagues_favourable: number
    top_league_profit_share_pct: number | null
    min_league_sample: number
  }
  matches: TriggeringMatch[]
  matches_total: number
  matches_truncated: boolean
  seasons?: SeasonBlock[]
}

export type SeasonBlock = {
  role: 'discovery' | 'validation'
  season_label: string | null
  run_v2_run_id: number
  verdict: OosStats['verdict'] | null
  null_confirm_prob?: number | null
  overall: PatternDetail['overall']
  baseline_win_rate_pct: number | null
  by_competition: LeagueBreakdown[]
  concentration: PatternDetail['concentration']
  matches: TriggeringMatch[]
  matches_total: number
  matches_truncated: boolean
}

export async function getPatternDetail(candidateId: number): Promise<PatternDetail> {
  return requestJson(
    `/api/admin/cecchino/research/run-v2-pattern-insight/candidates/${candidateId}/detail`,
  )
}

export async function getPatternInsightAnalytics(minN = 50): Promise<PatternInsightAnalytics> {
  return requestJson(`/api/admin/cecchino/research/run-v2-pattern-insight/analytics?min_n=${minN}`)
}

export async function getPatternInsightSummary(minN = 20): Promise<PatternInsightSummary> {
  return requestJson(`/api/admin/cecchino/research/run-v2-pattern-insight/summary?min_n=${minN}`)
}

export type PatternSort =
  | 'best'
  | 'roi_desc'
  | 'deviation_desc'
  | 'oos_roi_desc'
  | 'oos_deviation_desc'
  | 'oos_n_desc'

export async function getPatternInsightCandidates(params: {
  targetType?: PatternInsightTargetType
  targetKey?: string
  threshold?: number
  minN?: number
  verdict?: OosStats['verdict']
  sort?: PatternSort
  limit?: number
  offset?: number
}): Promise<PatternInsightCandidatesPage> {
  const qs = new URLSearchParams()
  if (params.targetType) qs.set('target_type', params.targetType)
  if (params.targetKey) qs.set('target_key', params.targetKey)
  if (params.threshold != null) qs.set('threshold', String(params.threshold))
  if (params.verdict) qs.set('verdict', params.verdict)
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
