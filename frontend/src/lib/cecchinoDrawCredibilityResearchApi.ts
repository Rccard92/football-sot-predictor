import { adminPostJson } from './api'

export type DrawCredibilityAuditRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
  only_eligible?: boolean
}

export type DrawCredibilityExclusionReason = {
  reason: string
  count: number
  pct_total: number
  pct_finished: number
}

export type DrawCredibilityLeagueRow = {
  country_name: string
  league_name: string
  competition_id: number | null
  total: number
  finished: number
  draws: number
  internal_usable: number
  market_usable: number
  internal_coverage_pct: number
  market_coverage_pct: number
}

export type DrawCredibilityMonthRow = {
  month: string
  total: number
  finished: number
  draws: number
  internal_usable: number
  market_usable: number
}

export type DrawCredibilityDebugSample = {
  today_fixture_id: number
  provider_fixture_id: number
  scan_date: string | null
  home_team: string | null
  away_team: string | null
  league_name: string | null
  reason: string
}

export type DrawCredibilityAuditSummary = {
  total_fixtures: number
  eligible_fixtures: number
  finished_fixtures: number
  finished_with_result: number
  draw_results: number
  non_draw_results: number
  with_cecchino_1x2_odds: number
  with_cecchino_1x2_probabilities: number
  with_complete_cecchino_1x2: number
  with_cecchino_under_2_5: number
  with_cecchino_over_2_5: number
  with_complete_cecchino_goal_pair: number
  with_book_1x2: number
  with_book_under_2_5: number
  with_book_over_2_5: number
  with_complete_book_goal_pair: number
  with_complete_book_markets: number
  usable_internal_research: number
  usable_market_comparison: number
}

export type DrawCredibilityAuditCoverage = {
  cecchino: {
    with_1x2_odds: number
    with_1x2_probabilities: number
    with_complete_1x2: number
    with_under_2_5: number
    with_over_2_5: number
    with_complete_goal_pair: number
    pct_complete_1x2: number
    pct_complete_goal_pair: number
  }
  book: {
    with_1x2: number
    with_under_2_5: number
    with_over_2_5: number
    with_complete_goal_pair: number
    with_complete_markets: number
    pct_complete_markets: number
  }
  research: {
    usable_internal: number
    usable_market_comparison: number
    pct_internal: number
    pct_internal_finished: number
    pct_market: number
    pct_market_finished: number
  }
}

export type DrawCredibilityAuditResponse = {
  status: string
  version: string
  filters: {
    date_from: string
    date_to: string
    competition_id: number | null
    only_eligible: boolean
  }
  summary: DrawCredibilityAuditSummary
  coverage: DrawCredibilityAuditCoverage
  target_distribution: {
    draws: number
    non_draws: number
    draw_rate_pct: number
  }
  exclusion_reasons: DrawCredibilityExclusionReason[]
  by_league: DrawCredibilityLeagueRow[]
  by_month: DrawCredibilityMonthRow[]
  debug_samples: DrawCredibilityDebugSample[]
  warnings: string[]
}

export async function postDrawCredibilityAudit(
  body: DrawCredibilityAuditRequest,
  opts?: { signal?: AbortSignal },
): Promise<DrawCredibilityAuditResponse> {
  return adminPostJson<DrawCredibilityAuditResponse>(
    '/api/admin/cecchino/research/draw-credibility/audit',
    {
      date_from: body.date_from,
      date_to: body.date_to,
      competition_id: body.competition_id ?? null,
      only_eligible: body.only_eligible ?? true,
    },
    opts,
  )
}

export type DrawCredibilityCohort =
  | 'eligible_primary'
  | 'all_usable_sensitivity'
  | 'market_subset'

export type DrawCredibilityDatasetRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
  cohort?: DrawCredibilityCohort
  page?: number
  page_size?: number
}

export type DrawCredibilityCohortSummary = {
  candidate_rows_before_dedup: number
  unique_provider_fixtures: number
  duplicates_removed_within_cohort: number
  rows_with_valid_target: number
  rows_with_internal_features: number
  rows_with_market_features: number
  leakage_safe: number
  leakage_unknown: number
  leakage_unsafe: number
  removed_no_target: number
  removed_no_pre_match_snapshot: number
  removed_leakage: number
  removed_invalid_features: number
  final_dataset_rows: number
  draws: number
  non_draws: number
  draw_rate_pct: number
  /** @deprecated legacy mirror */
  raw_rows_found?: number
  /** @deprecated legacy mirror */
  duplicate_rows_collapsed?: number
}

export type GlobalPipelineSummary = {
  raw_database_rows: number
  unique_provider_fixtures: number
  global_duplicates_collapsed: number
  groups_with_built_row: number
  groups_excluded: number
  groups_with_internal_features: number
  groups_without_supported_cecchino_final: number
  groups_without_target: number
  groups_without_pre_match_snapshot: number
  groups_leakage_unknown: number
  groups_leakage_unsafe: number
  all_internal_safe_rows: number
}

export type CohortAntiLeakage = {
  safe: number
  unknown: number
  unsafe: number
  excluded_no_pre_match_snapshot: number
}

export type GlobalExclusionItem = {
  reason: string
  label: string
  count: number
  pct_unique_fixtures: number
}

export type GlobalExclusionBreakdown = {
  first_blocking_reason: boolean
  priority_order: string[]
  items: GlobalExclusionItem[]
  total_excluded_groups: number
}

export type CohortConsistencyRow = {
  cohort: DrawCredibilityCohort
  label: string
  expected_from_audit: number
  row_level_candidates: number
  unique_after_dedup: number
  duplicates_removed_within_cohort: number
  removed_for_no_target: number
  removed_for_no_snapshot: number
  removed_for_leakage: number
  removed_for_invalid_internal_features: number
  final_dataset_rows: number
  delta_vs_audit: number
  explanation: string
}

export type VersionDistributionBlock = Record<string, DrawCredibilityVersionRow[]>

export type DrawCredibilityVersionRow = {
  version: string
  count: number
  pct: number
}

export type DrawCredibilityDatasetRow = {
  provider_fixture_id: number
  local_fixture_id: number | null
  today_fixture_id_feature: number
  today_fixture_id_target: number
  scan_date_feature: string | null
  scan_date_target: string | null
  kickoff: string | null
  country_name: string | null
  league_name: string | null
  competition_id: number | null
  home_team_name: string | null
  away_team_name: string | null
  eligibility_status_feature: string | null
  cohort: string
  draw_ft: number
  ft_home: number
  ft_away: number
  ft_score: string
  result_1x2: string
  quota_cecchino_1: number | null
  quota_cecchino_x: number | null
  quota_cecchino_2: number | null
  prob_x_norm: number | null
  x_rank: number | null
  x_tied_for_top: boolean
  f36_signed: number | null
  f36_abs: number | null
  f36_score_existing: number | null
  f36_class_existing: string | null
  dominant_sign: string | null
  dominance_pp: number | null
  conviction_index_candidate: number | null
  conviction_class_candidate: string | null
  probability_gap_1_2_pp: number | null
  probability_balance_index: number | null
  gap_coherence_index_candidate: number | null
  gap_coherence_class_candidate: string | null
  quota_under_2_5_cecchino: number | null
  quota_over_2_5_cecchino: number | null
  quota_book_x: number | null
  deviation_x_pp: number | null
  market_deviation_mean_pp: number | null
  leakage_status: string
  feature_snapshot_at: string | null
  target_snapshot_at: string | null
  has_market_features?: boolean
}

export type DrawCredibilityDatasetResponse = {
  status: string
  version: string
  filters: {
    date_from: string
    date_to: string
    competition_id: number | null
    cohort: DrawCredibilityCohort
    page: number
    page_size: number
  }
  global_pipeline: GlobalPipelineSummary
  selected_cohort_summary: DrawCredibilityCohortSummary
  cohort_summaries: Record<DrawCredibilityCohort, DrawCredibilityCohortSummary>
  anti_leakage_global: CohortAntiLeakage
  anti_leakage_selected: CohortAntiLeakage
  version_distribution_global: VersionDistributionBlock
  version_distribution_selected: VersionDistributionBlock
  global_exclusions: GlobalExclusionBreakdown
  cohort_consistency: CohortConsistencyRow[]
  primary_summary: DrawCredibilityCohortSummary
  sensitivity_summary: DrawCredibilityCohortSummary
  market_summary: DrawCredibilityCohortSummary
  deduplication: {
    raw_rows: number
    unique_provider_fixtures: number
    duplicates_collapsed: number
  }
  /** @deprecated use anti_leakage_global */
  anti_leakage: CohortAntiLeakage
  target_distribution: {
    rows: number
    draws: number
    non_draws: number
    draw_rate_pct: number
  }
  /** @deprecated use version_distribution_selected */
  version_distribution: VersionDistributionBlock
  consistency_checks: {
    expected_primary_from_audit: number
    expected_sensitivity_from_audit: number
    expected_market_from_audit: number
    actual_primary_rows: number
    actual_sensitivity_rows: number
    actual_market_rows: number
    difference_primary_vs_audit: number
    difference_sensitivity_vs_audit: number
    difference_market_vs_audit: number
    difference_reason: string
    duplicates_removed: number
    leakage_removed: number
    version_removed: number
    invalid_features_removed: number
  }
  pagination: {
    page: number
    page_size: number
    total_rows: number
    total_pages: number
  }
  rows: DrawCredibilityDatasetRow[]
  warnings: string[]
}

export function buildDrawCredibilityDatasetCsvFilename(
  cohort: DrawCredibilityCohort,
  dateFrom: string,
  dateTo: string,
): string {
  return `cecchino_draw_credibility_${cohort}_${dateFrom}_${dateTo}.csv`
}

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

function datasetRequestBody(body: DrawCredibilityDatasetRequest) {
  return {
    date_from: body.date_from,
    date_to: body.date_to,
    competition_id: body.competition_id ?? null,
    cohort: body.cohort ?? 'eligible_primary',
    page: body.page ?? 1,
    page_size: body.page_size ?? 100,
  }
}

export async function postDrawCredibilityDataset(
  body: DrawCredibilityDatasetRequest,
  opts?: { signal?: AbortSignal },
): Promise<DrawCredibilityDatasetResponse> {
  return adminPostJson<DrawCredibilityDatasetResponse>(
    '/api/admin/cecchino/research/draw-credibility/dataset',
    datasetRequestBody(body),
    opts,
  )
}

export async function postDrawCredibilityDatasetExportCsv(
  body: Omit<DrawCredibilityDatasetRequest, 'page' | 'page_size'>,
  opts?: { signal?: AbortSignal },
): Promise<{ blob: Blob; filename: string }> {
  const base = getApiBase()
  const res = await fetch(`${base}/api/admin/cecchino/research/draw-credibility/dataset/export.csv`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(datasetRequestBody({ ...body, page: 1, page_size: 100 })),
    signal: opts?.signal,
  })
  if (!res.ok) {
    let message = res.statusText
    const ct = res.headers.get('content-type') ?? ''
    if (ct.includes('application/json')) {
      try {
        const parsed = (await res.json()) as { detail?: string; message?: string }
        message = parsed.detail ?? parsed.message ?? message
      } catch {
        /* ignore */
      }
    }
    throw new Error(message || `HTTP ${res.status}`)
  }
  const ct = res.headers.get('content-type') ?? ''
  if (!ct.includes('text/csv')) {
    throw new Error('Risposta non CSV: verifica VITE_API_BASE_URL e endpoint backend')
  }
  const disposition = res.headers.get('content-disposition') ?? ''
  const match = /filename="([^"]+)"/.exec(disposition)
  const fallback = buildDrawCredibilityDatasetCsvFilename(
    body.cohort ?? 'eligible_primary',
    body.date_from,
    body.date_to,
  )
  return { blob: await res.blob(), filename: match?.[1] ?? fallback }
}

export const DRAW_CREDIBILITY_COHORT_LABELS: Record<DrawCredibilityCohort, string> = {
  eligible_primary: 'Primary (eligible + safe)',
  all_usable_sensitivity: 'Sensitivity (interno + safe)',
  market_subset: 'Market (Book completo + safe)',
}

export type DrawCredibilityStatisticsRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
  bin_count?: number
  min_group_size?: number
  bootstrap_iterations?: number
  random_seed?: number
}

export type WilsonCi = {
  lower_pct: number | null
  upper_pct: number | null
}

export type DrawCredibilityCohortTargetSummary = {
  rows: number
  draws: number
  non_draws: number
  draw_rate_pct: number
  wilson_ci_95: WilsonCi
  first_kickoff: string | null
  last_kickoff: string | null
  time_span_days: number
  distinct_match_days: number
  distinct_league_names_count?: number
  distinct_country_league_pairs_count?: number
  distinct_countries_count?: number
  /** @deprecated prefer distinct_league_names_count */
  league_count: number
  /** @deprecated prefer distinct_countries_count */
  country_count: number
}

export type DrawCredibilityBootstrapAuc = {
  original_directional_auc: number | null
  bootstrap_mean_directional_auc: number | null
  directional_auc_ci_lower: number | null
  directional_auc_ci_upper: number | null
  original_discriminative_auc: number | null
  discriminative_auc_ci_lower: number | null
  discriminative_auc_ci_upper: number | null
  valid_bootstrap_iterations: number
  /** @deprecated legacy alias of bootstrap_mean_directional_auc */
  auc?: number | null
  /** @deprecated legacy alias of directional_auc_ci_lower */
  auc_ci_lower?: number | null
  /** @deprecated legacy alias of directional_auc_ci_upper */
  auc_ci_upper?: number | null
}

export type DrawCredibilityFeatureLeaderboardRow = {
  feature: string
  type: string
  count: number | null
  missing_pct: number | null
  /** Alias opzionale; il backend invia tipicamente `feature_family`. */
  family?: string | null
  feature_family?: string | null
  directional_auc: number | null
  discriminative_auc: number | null
  bootstrap: DrawCredibilityBootstrapAuc | null
  pearson: number | null
  spearman: number | null
  trend: string
  best_bin_draw_rate: number | null
  worst_bin_draw_rate: number | null
  spread_pp: number | null
  reliability_status: string
  stability_status?: string | null
  interpretation: string
}

export type DrawCredibilityFeatureFamilyMeta = {
  members?: string[]
  preferred_representative?: string | null
  directional_preferred?: string | null
  note?: string
  [key: string]: unknown
}

export type DrawCredibilityBoundarySource =
  | 'primary'
  | 'market_subset'
  | 'categorical'
  | 'cohort'
  | string

export type DrawCredibilityColumnType = 'quantile' | 'categorical' | string

export type DrawCredibilityInteractionCell = {
  row_dimension?: string
  row_category: string
  column_dimension?: string
  column_category: string
  column_type?: DrawCredibilityColumnType
  /** Indice bin 1-based per colonne quantile; null se categoriale. */
  column_bin_index?: number | null
  column_lower_bound?: number | null
  column_upper_bound?: number | null
  column_lower_inclusive?: boolean | null
  column_upper_inclusive?: boolean | null
  boundary_source?: DrawCredibilityBoundarySource
  column_boundaries?: number[]
  count: number
  draws: number
  non_draws?: number
  reliable: boolean
  suppressed: boolean
  suppression_reason?: string | null
  /** Null quando suppressed=true. */
  draw_rate_pct?: number | null
  /** Null quando suppressed=true. */
  wilson_ci_95?: WilsonCi | null
  /** Null quando suppressed=true. */
  lift_vs_baseline_pp?: number | null
  [key: string]: unknown
}

export type DrawCredibilityInteractionBlock = {
  interaction_key: string
  label: string
  row_dimension: string
  column_dimension: string
  column_type?: DrawCredibilityColumnType
  boundary_source?: DrawCredibilityBoundarySource
  column_boundaries?: number[]
  primary_cells: DrawCredibilityInteractionCell[]
  sensitivity_cells: DrawCredibilityInteractionCell[]
  summary?: Record<string, unknown>
  [key: string]: unknown
}

export type DrawCredibilityBootstrapRoiCi = {
  lower_pct?: number | null
  upper_pct?: number | null
  crosses_zero?: boolean | null
  /** @deprecated */
  lower?: number | null
  /** @deprecated */
  upper?: number | null
  /** @deprecated */
  ci_lower?: number | null
  /** @deprecated */
  ci_upper?: number | null
  [key: string]: unknown
}

export type DrawCredibilityPatternMarketMatching = {
  pattern_key?: string | null
  interaction_key?: string | null
  boundary_source?: DrawCredibilityBoundarySource
  applied_boundaries?: number[]
  applied_bin_index?: number | null
  primary_pattern_count?: number | null
  market_rows_examined?: number | null
  market_rows_matched?: number | null
  market_match_rate_pct?: number | null
  match_status?: string | null
  warnings?: string[]
  using_recomputed_boundaries?: boolean
  [key: string]: unknown
}

export type DrawCredibilityCandidatePattern = {
  pattern_key: string
  interaction_key: string
  description: string
  row_dimension?: string
  row_category?: string
  column_dimension?: string
  column_type?: DrawCredibilityColumnType
  column_category?: string
  column_bin_index?: number | null
  column_lower_bound?: number | null
  column_upper_bound?: number | null
  column_lower_inclusive?: boolean | null
  column_upper_inclusive?: boolean | null
  column_boundaries?: number[]
  boundary_source?: DrawCredibilityBoundarySource
  primary_count: number
  primary_draws: number
  primary_draw_rate_pct?: number | null
  primary_lift_pp?: number | null
  primary_ci?: WilsonCi | null
  sensitivity_count?: number
  sensitivity_draw_rate_pct?: number | null
  sensitivity_lift_pp?: number | null
  direction_consistent?: boolean
  rate_delta_pp?: number | null
  evidence_status?: string
  stability_status?: string
  warnings?: string[]
  market_rows_examined?: number | null
  market_rows_matched?: number | null
  market_match_rate_pct?: number | null
  match_status?: string | null
  market_roi_pct?: number | null
  market_roi_ci?: DrawCredibilityBootstrapRoiCi | null
  market_roi_reliable?: boolean | null
  market_match_warnings?: string[]
  [key: string]: unknown
}

export type DrawCredibilityPatternConsistencyChecks = {
  patterns_total?: number
  quantitative_patterns?: number
  categorical_patterns?: number
  patterns_with_primary_boundaries?: number
  patterns_missing_metadata?: number
  market_patterns_matched?: number
  market_patterns_without_rows?: number
  market_patterns_using_recomputed_boundaries?: number
  [key: string]: unknown
}

export type DrawCredibilityLeagueCountSemantics = {
  distinct_league_names_count?: string
  distinct_country_league_pairs_count?: string
  distinct_countries_count?: string
  league_stability_grouping?: string
  [key: string]: unknown
}

export type DrawCredibilityIsoWeekRow = {
  week_key: string
  first_date?: string | null
  last_date?: string | null
  rows: number
  draws: number
  draw_rate_pct: number | null
  wilson_ci_95?: WilsonCi
  [key: string]: unknown
}

export type DrawCredibilityChronologicalBlock = {
  block: string
  rows: number
  date_from?: string | null
  date_to?: string | null
  draws: number
  draw_rate_pct: number | null
  wilson_ci_95?: WilsonCi
  feature_aucs?: Record<string, number | null>
  [key: string]: unknown
}

export type DrawCredibilityTemporalStability = {
  short_observation_window: boolean
  time_span_days: number
  iso_weeks: DrawCredibilityIsoWeekRow[]
  chronological_blocks: DrawCredibilityChronologicalBlock[]
  feature_temporal_consistency?: Record<string, unknown>
  note?: string
  [key: string]: unknown
}

export type DrawCredibilityLeagueRowStats = {
  country_name: string
  league_name: string
  rows: number
  percentage_dataset: number | null
  draws: number
  draw_rate_pct: number | null
  wilson_ci_95?: WilsonCi
  is_others?: boolean
  [key: string]: unknown
}

export type DrawCredibilityLeagueStability = {
  leagues: DrawCredibilityLeagueRowStats[]
  top_5_share_pct: number | null
  top_10_share_pct: number | null
  hhi: number
  concentration_status: string
  fragmented_leagues: boolean
  reliable_league_count: number
  league_count: number
  distinct_country_league_pairs_count?: number
  note?: string
  [key: string]: unknown
}

export type DrawCredibilityRoiBlock = {
  group_key?: string
  label?: string
  boundary_source?: DrawCredibilityBoundarySource
  count?: number
  bets?: number
  wins?: number
  losses?: number
  win_rate_pct?: number | null
  roi_pct?: number | null
  reliable?: boolean
  ci_crosses_zero?: boolean | null
  bootstrap_roi_ci_95?: DrawCredibilityBootstrapRoiCi | null
  pattern_matching?: DrawCredibilityPatternMarketMatching
  warnings?: string[]
  [key: string]: unknown
}

export type DrawCredibilityMarketComparison = {
  rows_compared?: number
  delta_brier?: number | null
  delta_brier_skill_score?: number | null
  delta_log_loss?: number | null
  delta_auc?: number | null
  delta_ece?: number | null
  pct_cecchino_gt_book?: number | null
  pct_cecchino_lt_book?: number | null
  pct_approximately_equal_0_5pp?: number | null
  mean_signed_deviation_x?: number | null
  median_signed_deviation_x?: number | null
  mean_absolute_deviation_x?: number | null
  median_absolute_deviation_x?: number | null
  [key: string]: unknown
}

export type DrawCredibilityMarketAnalysis = {
  cecchino: Record<string, unknown>
  book: Record<string, unknown>
  comparison: DrawCredibilityMarketComparison
  roi: DrawCredibilityRoiBlock
  roi_breakdown: DrawCredibilityRoiBlock[]
  pattern_market_matching?: DrawCredibilityPatternMarketMatching[]
  warnings?: string[]
  methodological_warnings?: string[]
  [key: string]: unknown
}

export type DrawCredibilityNextPhaseRecommendation = {
  feature: string
  reason: string
  preferred_form: string
  representation?: string
  family?: string | null
  [key: string]: unknown
}

export type DrawCredibilityRedundantGroup = {
  features: string[]
  pearson?: number | null
  spearman?: number | null
  level?: string
  [key: string]: unknown
}

export type DrawCredibilityRecommendedRepresentative = {
  family: string
  representative: string
  members?: string[]
  note?: string
  [key: string]: unknown
}

export type DrawCredibilityResearchConclusions = {
  potentially_useful: string[]
  modest_candidates?: string[]
  weak_or_uncertain: string[]
  /** @deprecated prefer redundant_groups */
  redundant?: string[]
  redundant_groups?: DrawCredibilityRedundantGroup[]
  recommended_representatives?: DrawCredibilityRecommendedRepresentative[]
  non_linear_candidates: string[]
  candidate_interactions?: string[]
  unstable_features?: string[]
  requires_more_history: string[]
  next_phase_features: string[]
  next_phase_feature_recommendations?: DrawCredibilityNextPhaseRecommendation[]
  [key: string]: unknown
}

export type DrawCredibilityStatisticsPerformance = {
  dataset_build_ms: number
  enrichment_ms?: number
  univariate_ms?: number
  bootstrap_ms?: number
  interactions_ms?: number
  temporal_ms?: number
  league_ms?: number
  market_ms?: number
  conclusions_ms?: number
  statistics_compute_ms: number
  total_ms: number
  [key: string]: number | undefined
}

export type DrawCredibilityStatisticsResponse = {
  status: string
  version: string
  filters: DrawCredibilityStatisticsRequest & { random_seed: number }
  dataset_summary: {
    primary: DrawCredibilityCohortTargetSummary
    sensitivity: DrawCredibilityCohortTargetSummary
    market: DrawCredibilityCohortTargetSummary
  }
  research_maturity: {
    status: string
    sample_size: number
    positive_events: number
    time_span_days: number
    short_time_span: boolean
    fragmented_leagues: boolean
    warnings: string[]
  }
  target_baseline: {
    primary_draw_rate_pct: number
    sensitivity_draw_rate_pct: number
    market_draw_rate_pct: number
  }
  descriptive_statistics: {
    numeric: Array<Record<string, unknown>>
  }
  probability_calibration: {
    primary_cecchino_x: Record<string, unknown>
  }
  numeric_feature_analysis: Record<string, Array<Record<string, unknown>>>
  categorical_feature_analysis: Record<string, Array<Record<string, unknown>>>
  feature_leaderboard: DrawCredibilityFeatureLeaderboardRow[]
  feature_families?: Record<string, DrawCredibilityFeatureFamilyMeta>
  redundancy_analysis: {
    pearson_matrix: Record<string, Record<string, number | null>>
    spearman_matrix: Record<string, Record<string, number | null>>
    pairs: Array<Record<string, unknown>>
    candidate_groups: Array<{ features: string[]; expected: boolean }>
    feature_families?: Record<string, DrawCredibilityFeatureFamilyMeta>
  }
  primary_vs_sensitivity: {
    feature_comparisons: Array<Record<string, unknown>>
    sensitivity_only_fixtures: Record<string, unknown>
  }
  temporal_stability: DrawCredibilityTemporalStability
  league_stability: DrawCredibilityLeagueStability
  interaction_analysis: DrawCredibilityInteractionBlock[]
  candidate_patterns: DrawCredibilityCandidatePattern[]
  pattern_consistency_checks?: DrawCredibilityPatternConsistencyChecks
  pattern_market_matching?: DrawCredibilityPatternMarketMatching[]
  league_count_semantics?: DrawCredibilityLeagueCountSemantics
  market_analysis: DrawCredibilityMarketAnalysis
  research_conclusions: DrawCredibilityResearchConclusions
  /** Alias top-level opzionale delle raccomandazioni fase successiva. */
  next_phase_feature_recommendations?: DrawCredibilityNextPhaseRecommendation[]
  warnings: string[]
  performance: DrawCredibilityStatisticsPerformance
}

export type DrawCredibilityModelComparisonRequest = {
  date_from: string
  date_to: string
  competition_id?: number | null
  final_holdout_pct?: number
  inner_splits?: number
  bootstrap_iterations?: number
  random_seed?: number
}

export type DrawCredibilityOofPrediction = {
  provider_fixture_id: number | string | null
  kickoff: string | null
  draw_ft: number
  model_key: string
  fold_id: string
  predicted_draw_probability: number
  predicted_credibility_0_100: number
  is_market_row: boolean
  quota_book_x?: number | null
  prob_book_x_norm?: number | null
}

export type DrawCredibilityModelLeaderboardRow = {
  model_key: string
  model_label: string
  eligibility: string
  control_only?: boolean
  selected_C?: number | null
  development_mean_brier?: number | null
  development_brier_skill?: number | null
  development_log_loss?: number | null
  development_auc?: number | null
  holdout_brier?: number | null
  holdout_brier_skill?: number | null
  holdout_log_loss?: number | null
  holdout_auc?: number | null
  holdout_ece?: number | null
  top_quintile_lift?: number | null
  temporal_stability?: string
  coefficient_stability?: string
  complexity?: Record<string, unknown>
  warnings?: string[]
}

export type DrawCredibilityModelComparisonResponse = {
  status: string
  version: string
  filters: Record<string, unknown>
  dataset_summary: Record<string, unknown>
  feature_manifest: Record<string, unknown>
  split_definition?: Record<string, unknown>
  split_consistency_checks?: Record<string, unknown>
  model_definitions?: Array<Record<string, unknown>>
  best_C_by_model?: Record<string, { C?: number | null; mean_brier?: number | null }>
  development_cv_results?: Array<Record<string, unknown>>
  model_leaderboard?: DrawCredibilityModelLeaderboardRow[]
  final_holdout_results?: Array<Record<string, unknown>>
  coefficient_stability?: Record<string, Array<Record<string, unknown>>>
  calibration_analysis?: Record<string, Record<string, unknown>>
  marginal_contributions?: Array<Record<string, unknown>>
  oof_consistency_checks?: Record<string, unknown>
  oof_predictions?: DrawCredibilityOofPrediction[]
  primary_vs_sensitivity?: Record<string, unknown>
  market_oof_analysis?: Record<string, unknown>
  reduced_model_analysis?: Record<string, unknown>
  decision?: {
    status: string
    leading_model?: string | null
    reduced_model?: string | null
    reasons?: string[]
    limitations?: string[]
    required_next_history_days?: number
    production_change_allowed: boolean
  }
  warnings?: string[]
  performance?: Record<string, number>
}

export async function postDrawCredibilityStatisticalAnalysis(
  body: DrawCredibilityStatisticsRequest,
  opts?: { signal?: AbortSignal },
): Promise<DrawCredibilityStatisticsResponse> {
  return adminPostJson<DrawCredibilityStatisticsResponse>(
    '/api/admin/cecchino/research/draw-credibility/statistical-analysis',
    {
      date_from: body.date_from,
      date_to: body.date_to,
      competition_id: body.competition_id ?? null,
      bin_count: body.bin_count ?? 5,
      min_group_size: body.min_group_size ?? 20,
      bootstrap_iterations: body.bootstrap_iterations ?? 500,
      random_seed: body.random_seed ?? 42,
    },
    opts,
  )
}

export async function postDrawCredibilityModelComparison(
  body: DrawCredibilityModelComparisonRequest,
  opts?: { signal?: AbortSignal },
): Promise<DrawCredibilityModelComparisonResponse> {
  return adminPostJson<DrawCredibilityModelComparisonResponse>(
    '/api/admin/cecchino/research/draw-credibility/model-comparison',
    {
      date_from: body.date_from,
      date_to: body.date_to,
      competition_id: body.competition_id ?? null,
      final_holdout_pct: body.final_holdout_pct ?? 0.25,
      inner_splits: body.inner_splits ?? 3,
      bootstrap_iterations: body.bootstrap_iterations ?? 500,
      random_seed: body.random_seed ?? 42,
    },
    opts,
  )
}
