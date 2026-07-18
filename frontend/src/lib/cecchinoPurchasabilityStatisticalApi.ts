import { AdminHttpError, adminGetJson, adminPostJson } from './api'

export type PurchasabilityStatFilters = {
  date_from?: string
  date_to?: string
  competition_id?: number | null
  market_family?: string | null
  selection?: string | null
  bootstrap_iterations?: number
  seed?: number
}

export type PurchasabilityStatExportKind =
  | 'summary'
  | 'cohort_identity'
  | 'temporal_folds'
  | 'market_results'
  | 'univariate_evidence'
  | 'candidate_comparison'
  | 'marginal_contribution'
  | 'feature_decisions'
  | 'rating_benchmark'
  | 'readiness'

export type PurchasabilityFeatureDecision = {
  feature_name: string
  source?: string
  decision: string
  decision_reason?: string
  coverage?: number | null
  marginal_effect?: string[]
  temporal_stability?: string
  market_stability?: string
  deterministic_dependencies?: string[]
  evidence_axes?: {
    predictive_against_outcome?: number | null
    incremental_vs_model?: boolean
    incremental_vs_book?: boolean
    economic_ranking_evidence?: boolean
    residual_reliability_evidence?: boolean
  }
}

export type PurchasabilityCandidateSpec = {
  configuration: string
  markets?: string[]
  auc_mean?: number | null
  brier_mean?: number | null
  log_loss_mean?: number | null
  ece_mean?: number | null
  cohort_full_coverage_roi?: number | null
  roi_top_10pct_mean?: number | null
  roi_top_20pct_mean?: number | null
  roi_top_quintile_mean?: number | null
  delta_auc_vs_book_mean?: number | null
  delta_brier_vs_book_mean?: number | null
  contains_book_information?: boolean
  deterministic_book_dependencies?: string[]
  independent_evidence_status?: string
  independent_delta_auc_vs_book?: number | null
  independent_delta_brier_vs_book?: number | null
  independent_delta_log_loss_vs_book?: number | null
  independent_roi_top_10_vs_book?: number | null
  independent_roi_top_20_vs_book?: number | null
  temporal_stability?: string
  market_stability?: string
  markets_positive?: number | null
  markets_negative?: number | null
  status?: string
  candidate_decision?: string
  is_book_baseline_benchmark?: boolean
}

export type PurchasabilityPairedCI = {
  estimate?: number | null
  ci_low?: number | null
  ci_high?: number | null
  iterations?: number
  valid_iterations?: number
}

export type PurchasabilityMarginalRow = {
  market?: string
  spec?: string
  vs?: string
  comparison_role?:
    | 'independent_vs_book'
    | 'model_enrichment_diagnostic'
    | 'rating_diagnostic'
    | string
  delta_auc?: number | null
  delta_brier_improvement?: number | null
  delta_log_loss_improvement?: number | null
  delta_roi_top_10pct?: number | null
  delta_roi_top_20pct?: number | null
  classification?: string
  effect_classification?: string
  temporal_classification?: string
  market_classification?: string
  market_stability?: string
  fold_sign_consistency?: number | null
  positive_folds?: number
  negative_folds?: number
  confidence_intervals?: {
    delta_auc?: PurchasabilityPairedCI
    delta_roi_top_10pct?: PurchasabilityPairedCI
  }
}

export type PurchasabilityBookBaselineAssessment = {
  book_auc_mean?: number | null
  best_non_book_auc_mean?: number | null
  delta_best_non_book_vs_book?: number | null
  book_brier_mean?: number | null
  best_non_book_brier_mean?: number | null
  book_log_loss_mean?: number | null
  best_non_book_log_loss_mean?: number | null
  book_roi_top_10?: number | null
  best_non_book_roi_top_10?: number | null
  markets_where_book_is_best_auc?: string[]
  markets_where_candidate_beats_book?: string[]
  dominance_status?: string
  note?: string
}

export type PurchasabilityMarketResult = {
  market: string
  status?: string
  settled_rows?: number
  unique_fixtures?: number
  win_rate?: number | null
  cohort_full_coverage_roi?: number | null
  roi?: number | null
  avg_odds?: number | null
  avg_break_even?: number | null
  best_spec_without_rating?: string | null
  best_spec_auc?: number | null
  limitations?: string[]
  rating_benchmark?: Record<string, unknown>
  temporal_folds?: Array<Record<string, unknown>>
}

export type PurchasabilityStatisticalResearchResponse = {
  status: string
  version: string
  dataset_version: string
  research_banner?: string
  paired_comparisons_total?: number
  paired_comparisons_unique?: number
  paired_duplicates_removed?: number
  cohort_identity?: {
    settled_rows?: number
    unique_fixtures?: number
    date_min?: string | null
    date_max?: string | null
    markets?: string[]
    canonical_row_key_hash?: string
    fixture_identity_hash?: string
    target_hash?: string
  }
  data_quality?: Record<string, unknown>
  temporal_folds?: Array<Record<string, unknown>>
  market_results?: PurchasabilityMarketResult[]
  pooled_results?: Record<string, unknown>
  candidate_specifications?: PurchasabilityCandidateSpec[]
  feature_decisions?: PurchasabilityFeatureDecision[]
  marginal_contribution?: PurchasabilityMarginalRow[]
  rating_benchmark?: {
    conclusion?: string
    per_market?: Array<Record<string, unknown>>
    note?: string
  }
  book_baseline_assessment?: PurchasabilityBookBaselineAssessment
  phase_2b_readiness?: {
    recommended_next_step?: string
    rating_decision?: string
    blocking_issues?: string[]
    limitations?: string[]
    markets_evaluated?: string[]
    features_with_positive_stable_evidence?: string[]
    features_redundant?: string[]
    features_unstable?: string[]
    market_specific_features?: string[]
    model_enrichment_features?: string[]
    paired_positive_vs_book?: number
    paired_positive_vs_model?: number
    paired_positive_vs_rating?: number
    paired_comparisons_total?: number
    paired_comparisons_unique?: number
    paired_duplicates_removed?: number
    paired_positive_comparisons?: number
    paired_negative_comparisons?: number
    paired_uncertain_comparisons?: number
    independent_candidate_specs?: string[]
    model_enrichment_specs?: string[]
    book_baseline_dominance?: string
    residual_research_candidate?: boolean
    readiness_invariants_passed?: boolean
    readiness_invariant_errors?: string[]
    cohort_valid?: boolean
    temporal_cv_completed?: boolean
    [key: string]: unknown
  }
  limitations?: string[]
  elapsed_ms?: Record<string, number>
  filters?: PurchasabilityStatFilters
  no_db_writes?: boolean
  no_purchasability_formula?: boolean
}

export type PurchasabilityResearchJobStatus = {
  job_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | string
  current_stage?: string | null
  progress_message?: string | null
  created_at?: string
  started_at?: string | null
  completed_at?: string | null
  elapsed_seconds?: number | null
  filters?: PurchasabilityStatFilters
  statistical_version?: string
  dataset_version?: string
  result_available?: boolean
  error_code?: string | null
  error_message?: string | null
}

export type PurchasabilityResearchJobStartResponse = {
  status: string
  job_id: string
  reused: boolean
  poll_after_ms?: number
}

export const PURCHASABILITY_JOB_POLL_MS = 2000

const JOBS_BASE = '/api/admin/cecchino/research/purchasability/statistical-research/jobs'

function qs(filters: PurchasabilityStatFilters): string {
  const p = new URLSearchParams()
  if (filters.date_from) p.set('date_from', filters.date_from)
  if (filters.date_to) p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.market_family) p.set('market_family', filters.market_family)
  if (filters.selection) p.set('selection', filters.selection)
  if (filters.bootstrap_iterations != null) {
    p.set('bootstrap_iterations', String(filters.bootstrap_iterations))
  }
  if (filters.seed != null) p.set('seed', String(filters.seed))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** @deprecated Solo Console/debug — il FE usa i job async. */
export function statisticalResearchTimeoutMs(bootstrapIterations?: number | null): number {
  const iterations = bootstrapIterations ?? 200
  if (iterations > 500) return 1_200_000
  if (iterations > 200) return 600_000
  return 300_000
}

/** @deprecated Solo Console/debug — non usare nel flusso UI. */
export async function getPurchasabilityStatisticalResearch(
  filters: PurchasabilityStatFilters = {},
): Promise<PurchasabilityStatisticalResearchResponse> {
  const timeoutMs = statisticalResearchTimeoutMs(filters.bootstrap_iterations)
  return adminGetJson(
    `/api/admin/cecchino/research/purchasability/statistical-research${qs(filters)}`,
    { timeoutMs },
  )
}

export async function startPurchasabilityStatisticalJob(
  filters: PurchasabilityStatFilters = {},
): Promise<PurchasabilityResearchJobStartResponse> {
  return adminPostJson(
    JOBS_BASE,
    {
      date_from: filters.date_from ?? null,
      date_to: filters.date_to ?? null,
      competition_id: filters.competition_id ?? null,
      market_family: filters.market_family ?? null,
      selection: filters.selection ?? null,
      bootstrap_iterations: filters.bootstrap_iterations ?? 200,
      seed: filters.seed ?? 42,
    },
    { timeoutMs: 30_000 },
  )
}

export async function getPurchasabilityStatisticalJob(
  jobId: string,
): Promise<PurchasabilityResearchJobStatus> {
  return adminGetJson(`${JOBS_BASE}/${encodeURIComponent(jobId)}`, { timeoutMs: 15_000 })
}

export async function getPurchasabilityStatisticalJobSummary(
  jobId: string,
): Promise<PurchasabilityStatisticalResearchResponse> {
  return adminGetJson(`${JOBS_BASE}/${encodeURIComponent(jobId)}/summary`, {
    timeoutMs: 300_000,
  })
}

export async function getPurchasabilityStatisticalJobResult(
  jobId: string,
): Promise<PurchasabilityStatisticalResearchResponse> {
  return adminGetJson(`${JOBS_BASE}/${encodeURIComponent(jobId)}/result`, {
    timeoutMs: 300_000,
  })
}

export async function getActivePurchasabilityStatisticalJob(): Promise<{
  status: string
  job: PurchasabilityResearchJobStatus | null
}> {
  return adminGetJson(`${JOBS_BASE}/active`, { timeoutMs: 15_000 })
}

/** Formatta ms in "X min Y,Z s" (locale IT). */
export function formatElapsedMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms) || ms < 0) return '—'
  const totalSec = ms / 1000
  const minutes = Math.floor(totalSec / 60)
  const seconds = totalSec - minutes * 60
  const secStr = seconds.toLocaleString('it-IT', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
  if (minutes <= 0) return `${secStr} s`
  return `${minutes} min ${secStr} s`
}

export function formatPurchasabilityJobError(err: unknown): string {
  if (err instanceof AdminHttpError) {
    const body = err.body as Record<string, unknown> | null
    const code = body && typeof body === 'object' ? String(body.error || '') : ''
    if (err.status === 409 && code === 'purchasability_research_job_already_running') {
      return 'È già in esecuzione un’altra ricerca statistica.'
    }
    if (err.status === 404 && code === 'research_job_not_found_or_expired') {
      return 'Il job non è più disponibile, probabilmente a causa di un restart o di un nuovo deploy. Avvia nuovamente la ricerca.'
    }
    if (body && typeof body === 'object' && typeof body.error === 'string' && body.error) {
      return String(body.error)
    }
    return err.message
  }
  if (err instanceof Error) return err.message
  return String(err)
}

export function buildPurchasabilityStatExportUrl(
  kind: PurchasabilityStatExportKind,
  filters: PurchasabilityStatFilters = {},
): string {
  return `/api/admin/cecchino/research/purchasability/statistical-research/export/${kind}${qs(filters)}`
}
