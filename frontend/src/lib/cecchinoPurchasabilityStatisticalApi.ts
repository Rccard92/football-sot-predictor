import { adminGetJson } from './api'

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
  temporal_stability?: string
  market_stability?: string
  markets_positive?: number | null
  markets_negative?: number | null
  status?: string
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
  delta_auc?: number | null
  delta_brier_improvement?: number | null
  delta_roi_top_10pct?: number | null
  delta_roi_top_20pct?: number | null
  classification?: string
  temporal_classification?: string
  market_stability?: string
  fold_sign_consistency?: number | null
  positive_folds?: number
  negative_folds?: number
  confidence_intervals?: {
    delta_auc?: PurchasabilityPairedCI
    delta_roi_top_10pct?: PurchasabilityPairedCI
  }
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

export async function getPurchasabilityStatisticalResearch(
  filters: PurchasabilityStatFilters = {},
): Promise<PurchasabilityStatisticalResearchResponse> {
  return adminGetJson(
    `/api/admin/cecchino/research/purchasability/statistical-research${qs(filters)}`,
  )
}

export function buildPurchasabilityStatExportUrl(
  kind: PurchasabilityStatExportKind,
  filters: PurchasabilityStatFilters = {},
): string {
  return `/api/admin/cecchino/research/purchasability/statistical-research/export/${kind}${qs(filters)}`
}
