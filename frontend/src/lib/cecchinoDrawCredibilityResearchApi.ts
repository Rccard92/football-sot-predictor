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
