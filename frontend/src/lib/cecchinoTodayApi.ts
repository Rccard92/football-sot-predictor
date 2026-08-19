/**
 * Client API Cecchino Today — discovery giornaliera (separato da SOT e Cecchino classico).
 */

import { adminGetJson, adminPostJson, requestJson } from './api'

export type MatchDisplayStatus = 'upcoming' | 'live' | 'finished' | 'postponed' | 'cancelled' | 'unknown'

export type CecchinoTodayScanReport = {
  status: string
  version: string
  scan_date: string
  fixtures_found?: number
  total_discovered: number
  eligible: number
  excluded: Record<string, number>
  excluded_total?: number
  fixtures_processed?: number
  top_exclusion_reasons?: Array<{ status: string; count: number }>
  warnings: string[]
  errors?: string[]
  excluded_summary?: Record<string, number>
  message?: string
  result_summary?: CecchinoTodayScanJobResultSummary
  cleanup?: { deleted: number; cutoff_date: string }
  scan_meta?: CecchinoTodayScanMeta
}

export type CecchinoTodayScanStatus =
  | 'not_scanned'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'

export type CecchinoTodayDay = {
  date: string
  label: string
  is_today: boolean
  is_future: boolean
  is_scanned: boolean
  eligible_count: number
  excluded_count: number
  upcoming_count: number
  live_count: number
  finished_count: number
  last_scan_at: string | null
  scan_state: 'scanned' | 'not_scanned' | 'scanning' | 'error' | 'partial'
  status: 'available' | 'pending'
  scan_status?: CecchinoTodayScanStatus
  active_job_id?: string | null
  scan_job_status?: string | null
  scan_job_id?: string | null
}

/** Log debug solo in DEV — polling/selectedDay. */
export function logCecchinoTodayDebug(message: string, data?: unknown): void {
  if (import.meta.env.DEV) {
    if (data !== undefined) {
      console.debug(`[CecchinoToday] ${message}`, data)
    } else {
      console.debug(`[CecchinoToday] ${message}`)
    }
  }
}

export type CecchinoTodayDaysResponse = {
  status: string
  version: string
  timezone: string
  today: string
  tomorrow: string
  selected_default: string
  days: CecchinoTodayDay[]
}

export type CecchinoTodayScanJobStartResponse = {
  job_id?: string | null
  status: string
  scan_date: string
  message: string
  scan_meta?: CecchinoTodayScanMeta
}

export type CecchinoTodayEligibilityTransitions = {
  new_eligible?: number
  promoted_to_eligible?: number
  eligible_refreshed?: number
  eligible_preserved_refresh_failed?: number
  eligible_frozen_after_kickoff?: number
  eligible_preserved_terminal_status?: number
  started_never_eligible?: number
}

export type CecchinoTodayAutoScanMeta = {
  execution_source?: string
  execution_mode?: string
  execution_slot?: 'primary' | 'recovery' | string
  target_date?: string
  timezone?: string
  local_execution_date?: string
  attempt?: number
  lock_acquired?: boolean
  max_runtime_minutes?: number
}

export type CecchinoTodayBookCoverageBlock = {
  policy_version?: string
  betfair_primary_selection_count?: number
  bet365_fallback_selection_count?: number
  missing_selection_count?: number
  bet365_fallback_fixture_count?: number
  book_coverage_fixture_count?: number
  resolved_selection_count?: number
  total_selection_count?: number
  coverage_pct?: number | null
  /** MONITOR-01.1 integrity */
  selection_keys_count?: number
  expected_selection_count?: number
  actual_selection_count?: number
  consistent?: boolean | null
}

export type CecchinoTodayScanJobResultSummary = {
  fixtures_found?: number
  fixtures_discovered?: number
  fixtures_processed?: number
  fixtures_remaining?: number
  unprocessed_count?: number
  fixtures_censused?: number
  after_competition_filter?: number
  fixtures_after_competition_gate?: number
  fixtures_after_bookmaker_gate?: number
  fixtures_after_stats_gate?: number
  odds_checked?: number
  odds_from_cache?: number
  odds_from_api?: number
  odds_cache_hits?: number
  negative_cache_hits?: number
  stats_checked?: number
  bookmaker_fallback_count?: number
  /** Fixture con ≥1 selection Betfair (legacy). */
  betfair_primary_used?: number
  /** Selection canoniche risolte da Betfair primario. */
  betfair_primary_selection_count?: number
  /** Fixture con ≥1 selection Bet365 fallback (legacy). */
  bet365_fallback_used?: number
  /** Selection canoniche risolte via Bet365 fallback. */
  bet365_fallback_selection_count?: number
  /** Fixture con almeno una selection Bet365 fallback. */
  bet365_fallback_fixture_count?: number
  /** Fixture stats-qualified nel denominatore full Book coverage. */
  book_coverage_fixture_count?: number
  /** Selection canoniche ancora N/D dopo Betfair + Bet365. */
  book_still_missing_after_fallback?: number
  book_coverage_pct?: number | null
  book_coverage?: CecchinoTodayBookCoverageBlock
  bookmaker_mode?: string
  book_policy_version?: string
  /** MONITOR-01.1 integrity (len canonical keys). */
  book_selection_keys_count?: number
  book_coverage_expected_selection_count?: number
  book_coverage_actual_selection_count?: number
  book_coverage_consistent?: boolean | null
  api_calls?: Record<string, number>
  api_calls_total?: number
  api_calls_by_endpoint?: Record<string, number>
  odds_strategy?: Record<string, number>
  duration_seconds?: number
  scan_date?: string
  execution_date?: string
  stopped_at_fixture?: number | null
  stopped_at_endpoint?: string | null
  excluded_funnel?: {
    competition?: number
    bookmaker?: number
    market_1x2?: number
    stats?: number
    cecchino?: number
  }
  api_usage?: {
    total_calls?: number
    cache_hits?: number
    negative_cache_hits?: number
    estimated_remaining_daily_budget?: number
    by_endpoint?: Record<string, number>
  }
  eligibility_transitions?: CecchinoTodayEligibilityTransitions
  protected_eligible_total?: number
  protected_snapshot_overwrite_blocked?: number
  snapshot_eligible_protection_active?: boolean
  auto_scan?: CecchinoTodayAutoScanMeta
  diagnostic_code?: string
}

export type CecchinoTodayBookCoverageView = {
  betfairPrimarySelectionCount: number
  bet365FallbackSelectionCount: number
  missingSelectionCount: number
  bet365FallbackFixtureCount: number
  bookCoverageFixtureCount: number
  resolvedSelectionCount: number
  totalSelectionCount: number
  coveragePct: number | null
  policyVersion: string | null
  /** True se almeno un counter selection è presente (anche a zero dopo quote processate). */
  hasBookFields: boolean
  /** True se total_considered > 0 (si può mostrare coverage). */
  hasQuoteData: boolean
  /** MONITOR-01.1: null/undefined = job legacy senza integrity fields. */
  selectionKeysCount: number | null
  expectedSelectionCount: number | null
  actualSelectionCount: number | null
  consistent: boolean | null
  /** True solo quando integrity presente e consistent === false. */
  coverageInconsistent: boolean
}

export function getScanJobBookCoverage(
  summary: CecchinoTodayScanJobResultSummary | null | undefined,
): CecchinoTodayBookCoverageView {
  const bc = summary?.book_coverage
  const hasTop =
    summary?.betfair_primary_selection_count != null ||
    summary?.bet365_fallback_selection_count != null ||
    summary?.book_still_missing_after_fallback != null ||
    summary?.book_coverage_pct != null ||
    summary?.bet365_fallback_fixture_count != null ||
    summary?.book_coverage_fixture_count != null ||
    bc != null
  const bf = Number(
    bc?.betfair_primary_selection_count ?? summary?.betfair_primary_selection_count ?? 0,
  )
  const b365 = Number(
    bc?.bet365_fallback_selection_count ?? summary?.bet365_fallback_selection_count ?? 0,
  )
  const missing = Number(
    bc?.missing_selection_count ?? summary?.book_still_missing_after_fallback ?? 0,
  )
  const fixtureFallback = Number(
    bc?.bet365_fallback_fixture_count ?? summary?.bet365_fallback_fixture_count ?? 0,
  )
  const coverageFixtureCount = Number(
    bc?.book_coverage_fixture_count ?? summary?.book_coverage_fixture_count ?? 0,
  )
  const resolved =
    bc?.resolved_selection_count != null
      ? Number(bc.resolved_selection_count)
      : bf + b365
  const total =
    bc?.total_selection_count != null
      ? Number(bc.total_selection_count)
      : resolved + missing
  let coveragePct: number | null =
    bc?.coverage_pct !== undefined
      ? bc.coverage_pct
      : summary?.book_coverage_pct !== undefined
        ? summary.book_coverage_pct
        : null
  if (coveragePct == null && total > 0) {
    coveragePct = Math.round((resolved / total) * 1000) / 10
  }
  if (total <= 0) {
    coveragePct = null
  }

  const consistentRaw =
    bc?.consistent !== undefined
      ? bc.consistent
      : summary?.book_coverage_consistent !== undefined
        ? summary.book_coverage_consistent
        : undefined
  const consistent: boolean | null =
    consistentRaw === true || consistentRaw === false ? consistentRaw : null
  const coverageInconsistent = consistent === false
  // PERF-01 / MONITOR-01.1: non mostrare % apparentemente valida se counters incoerenti
  if (coverageInconsistent) {
    coveragePct = null
  }

  const selectionKeysCount =
    bc?.selection_keys_count != null
      ? Number(bc.selection_keys_count)
      : summary?.book_selection_keys_count != null
        ? Number(summary.book_selection_keys_count)
        : null
  const expectedSelectionCount =
    bc?.expected_selection_count != null
      ? Number(bc.expected_selection_count)
      : summary?.book_coverage_expected_selection_count != null
        ? Number(summary.book_coverage_expected_selection_count)
        : null
  const actualSelectionCount =
    bc?.actual_selection_count != null
      ? Number(bc.actual_selection_count)
      : summary?.book_coverage_actual_selection_count != null
        ? Number(summary.book_coverage_actual_selection_count)
        : null

  const policyVersion =
    bc?.policy_version ||
    summary?.book_policy_version ||
    summary?.bookmaker_mode ||
    null
  return {
    betfairPrimarySelectionCount: bf,
    bet365FallbackSelectionCount: b365,
    missingSelectionCount: missing,
    bet365FallbackFixtureCount: fixtureFallback,
    bookCoverageFixtureCount: coverageFixtureCount,
    resolvedSelectionCount: resolved,
    totalSelectionCount: total,
    coveragePct,
    policyVersion,
    hasBookFields: hasTop,
    hasQuoteData: total > 0,
    selectionKeysCount,
    expectedSelectionCount,
    actualSelectionCount,
    consistent,
    coverageInconsistent,
  }
}

/** Formatta coverage % con 1 decimale in locale IT (es. 97,5%). */
export function formatBookCoveragePct(pct: number | null | undefined): string | null {
  if (pct == null || Number.isNaN(Number(pct))) return null
  return `${Number(pct).toFixed(1).replace('.', ',')}%`
}

export type CecchinoTodayScanJob = {
  job_id: string
  scan_date: string
  timezone: string
  force_rescan: boolean
  status: string
  current_step: string | null
  progress_current: number
  progress_total: number | null
  progress_pct: number | null
  fixtures_found: number
  fixtures_checked: number
  odds_checked: number
  eligible_count: number
  excluded_count: number
  excluded_summary: Record<string, number>
  result_summary: CecchinoTodayScanJobResultSummary | null
  warnings: string[]
  errors: string[]
  started_at: string | null
  finished_at: string | null
  created_at?: string | null
  updated_at?: string | null
}

export const SCAN_JOB_POLL_MS = 2500

/** Estrae metriche API dal job (compatibile job legacy senza result_summary). */
export function getScanJobApiMetrics(job: CecchinoTodayScanJob): {
  apiCallsTotal: number
  oddsApi: number
  oddsCache: number
  negativeCache: number
  teams: number
  fixtures: number
  budgetRemaining: number | null
} {
  const rs = job.result_summary
  const apiCalls = rs?.api_calls ?? rs?.api_calls_by_endpoint ?? {}
  const apiUsage = rs?.api_usage
  return {
    apiCallsTotal: Number(rs?.api_calls_total ?? apiUsage?.total_calls ?? 0),
    oddsApi: Number(apiCalls.odds ?? apiUsage?.by_endpoint?.odds ?? 0),
    oddsCache: Number(rs?.odds_cache_hits ?? rs?.odds_from_cache ?? 0),
    negativeCache: Number(rs?.negative_cache_hits ?? apiUsage?.negative_cache_hits ?? 0),
    teams: Number(apiCalls.teams ?? apiUsage?.by_endpoint?.teams ?? 0),
    fixtures: Number(apiCalls.fixtures ?? apiUsage?.by_endpoint?.fixtures ?? 0),
    budgetRemaining:
      apiUsage?.estimated_remaining_daily_budget != null
        ? Number(apiUsage.estimated_remaining_daily_budget)
        : null,
  }
}

/** Percentuale avanzamento job — fallback se progress_pct assente o 0. */
export function computeScanJobProgressPct(job: CecchinoTodayScanJob): number {
  if (job.status === 'completed') return 100
  if (job.progress_pct != null && job.progress_pct > 0) return job.progress_pct
  const cur = job.progress_current ?? job.fixtures_checked ?? 0
  const tot = job.progress_total
  if (cur > 0 && tot != null && tot > 0) {
    return Math.min(100, Math.round((cur / tot) * 1000) / 10)
  }
  return 0
}

export const SCAN_STEP_LABELS: Record<string, string> = {
  fetching_fixtures: 'Recupero partite',
  filtering_competitions: 'Filtro competizioni',
  fetching_odds: 'Recupero quote bookmaker',
  importing_stats: 'Import statistiche',
  calculating_cecchino: 'Calcolo Cecchino',
  validating_eligibility: 'Validazione eleggibilità',
  saving_snapshots: 'Salvataggio snapshot',
  completed: 'Completato',
  provider_quota_exhausted: 'Richieste API esaurite',
}

export type CecchinoTodayScanMeta = {
  has_scan: boolean
  is_scanned?: boolean
  eligible_count: number
  excluded_count: number
  upcoming_count?: number
  live_count?: number
  finished_count?: number
  last_scan_at: string | null
  day_status: 'available' | 'pending'
  scan_state?: string
}

export type CecchinoTodayScoreSide = {
  home: number | null
  away: number | null
  available: boolean
}

export type CecchinoTodayScore = {
  halftime: CecchinoTodayScoreSide
  fulltime: CecchinoTodayScoreSide
}

export type CecchinoTodayRecommendedPrediction = {
  status: string
  label: string
  market: string | null
  confidence: number | null
}

export type CecchinoTodayListFixture = {
  today_fixture_id: number
  id: number
  provider_fixture_id: number
  local_fixture_id: number | null
  competition_id: number | null
  home_team_name: string | null
  away_team_name: string | null
  home_team_logo_url: string | null
  away_team_logo_url: string | null
  kickoff: string | null
  status: MatchDisplayStatus
  status_label: string
  score: CecchinoTodayScore
  cecchino_recommended_prediction: CecchinoTodayRecommendedPrediction
  kpi_status: string
  signals_status: string
}

export type CecchinoTodayListCountry = {
  country_name: string
  country_flag_url: string | null
  leagues: Array<{
    league_name: string
    league_logo_url: string | null
    fixtures: CecchinoTodayListFixture[]
  }>
}

export type CecchinoTodayListSummary = {
  eligible_count: number
  upcoming_count: number
  live_count: number
  finished_count: number
  excluded_count: number
  last_scan_at: string | null
}

export type CecchinoTodayListResponse = {
  status: string
  version: string
  date: string
  scan_date: string
  is_scanned: boolean
  total: number
  summary: CecchinoTodayListSummary
  filters: {
    countries: string[]
    leagues: string[]
    statuses: string[]
  }
  countries: CecchinoTodayListCountry[]
  scan_meta?: CecchinoTodayScanMeta
}

export type CecchinoTodayUpdateResultsResponse = {
  status: string
  version?: string
  date: string
  fixtures_checked: number
  results_updated: number
  still_upcoming: number
  live: number
  failed: Array<{ provider_fixture_id: number; error: string }>
  warnings: string[]
  api_calls?: number
  signals_evaluated?: number
  signals_pending?: number
}

export type CecchinoKpiV2Row = {
  market_key: string
  segno: string
  label?: string
  quota_book: number | null
  quota_cecchino: number | null
  prob_book: number | null
  prob_cecchino: number | null
  vantaggio_prob: number | null
  edge_pct: number | null
  score_acquisto: number | null
  rating: number | null
  rating_label: string | null
  status: string
  book_source?: string
  cecchino_source?: string | null
  bookmaker_name?: string | null
  provider_bookmaker_id?: number | null
  book_fallback_used?: boolean | null
}

export type CecchinoOddsMeta = {
  odds_source?: string | null
  odds_fetched_at?: string | null
  odds_cached_at?: string | null
  last_betfair_refresh_at?: string | null
  last_book_refresh_at?: string | null
  is_cached?: boolean | null
  odds_updated_at?: string | null
  book_policy_version?: string | null
  policy_label?: string | null
}

export type CecchinoKpiV2Panel = {
  version: string
  book_policy_version?: string
  columns?: string[]
  bookmaker?: {
    name: string
    provider_bookmaker_id: number
    provider_source: string
    policy_label?: string
    primary_name?: string
    fallback_name?: string
    primary_provider_bookmaker_id?: number
    fallback_provider_bookmaker_id?: number
  }
  bookmaker_status?: string
  book_resolution_stats?: {
    betfair_primary_used?: boolean
    bet365_fallback_used?: boolean
    bet365_fallback_selection_count?: number
    book_still_missing_after_fallback?: number
  }
  odds_meta?: CecchinoOddsMeta
  rows: CecchinoKpiV2Row[]
  warnings?: string[]
}

export type CecchinoPurchasabilityObservationalItem = {
  status: 'available' | 'insufficient_data' | 'not_evaluated'
  sample_size: number
  roi_pct: number | null
  score_band?: string | null
  candidate_version?: string | null
  market_key?: string | null
}

export type CecchinoPurchasabilityPreviewItem = {
  market_key: string
  selection?: string | null
  status: 'available' | 'partial' | 'unavailable'
  calculation_quality?: 'full' | 'partial' | null
  score: number | null
  raw_score?: number | null
  raw_pre_gate_score?: number | null
  class?: 'Molto Bassa' | 'Bassa' | 'Media' | 'Alta' | 'Molto Alta' | null
  reading?: string | null
  phase_1_score?: number | null
  phase_2_score?: number | null
  reason_codes?: string[]
  positive_value_gate?: {
    status?: string | null
    reason_codes?: string[]
  } | null
  normalization_profile_version?: string | null
  normalization_profile_hash?: string | null
}

export type CecchinoPurchasabilityPreviewSnapshot = {
  snapshot_version: string
  contract_version: string
  feature_version: string
  candidate_version: string
  candidate_name: string
  status: 'ok' | 'partial' | 'unavailable'
  source_mode?: 'persisted_pre_match_snapshot' | 'derived_read_only_from_stored_snapshot'
  items: CecchinoPurchasabilityPreviewItem[]
  summary?: Record<string, unknown>
  pre_match_only: boolean
  normalization_profile_version?: string | null
  normalization_profile_hash?: string | null
  normalization_profile_cutoff?: string | null
  registry_status?: string | null
  warnings?: string[]
}

export type CecchinoPurchasabilityComparisonMarketItem = {
  v1_1_score: number | null
  v2_score: number | null
  delta_v2_minus_v1_1: number | null
  comparison_status: 'available' | 'partial' | 'unavailable' | string
}

export type CecchinoPurchasabilityComparison = {
  items: Record<string, CecchinoPurchasabilityComparisonMarketItem>
}

export type CecchinoPurchasabilityV3Status =
  | 'available'
  | 'partial'
  | 'unavailable'
  | 'not_applicable'
  | string

export type CecchinoPurchasabilityV3Class =
  | 'Molto Bassa'
  | 'Bassa'
  | 'Media'
  | 'Alta'
  | 'Molto Alta'
  | string

export type CecchinoPurchasabilityV3GateStatus =
  | 'passed'
  | 'failed_non_positive_edge'
  | 'failed_non_positive_probability_advantage'
  | 'failed_multiple_non_positive_components'
  | 'unavailable_inputs'
  | 'unsupported_market'
  | string

export type CecchinoPurchasabilityV3Penalty = {
  key?: string
  label?: string | null
  raw_inputs?: Record<string, number | string | boolean | null>
  threshold_start?: number | null
  threshold_full?: number | null
  severity?: number | null
  max_points?: number | null
  penalty_points?: number | null
  applied?: boolean
  explanation?: string | null
}

export type CecchinoPurchasabilityV3Gate = {
  gate_status?: CecchinoPurchasabilityV3GateStatus | null
  gate_reason_codes?: string[]
  edge_available?: boolean | null
  edge_positive?: boolean | null
  probability_advantage_available?: boolean | null
  probability_advantage_positive?: boolean | null
  gate_reading?: string | null
}

export type CecchinoPurchasabilityV3FamilyMarketRow = {
  market_key?: string | null
  market_label?: string | null
  market_family?: string | null
  edge_pct?: number | null
  gate_status?: string | null
  gate_passed?: boolean | null
  is_selected?: boolean | null
  is_leader?: boolean | null
  is_second?: boolean | null
  rank_by_edge?: number | null
  included_in_family?: boolean | null
  included_in_gate_passed_comparison?: boolean | null
  score?: number | null
  edge_diff_from_leader?: number | null
}

export type CecchinoPurchasabilityV3Family = {
  market_family?: string | null
  market_family_label?: string | null
  selected_is_family_edge_leader?: boolean | null
  family_edge_leader_key?: string | null
  family_edge_leader_edge_pct?: number | null
  family_edge_second_key?: string | null
  family_edge_second_edge_pct?: number | null
  family_edge_gap_pct?: number | null
  family_edge_deficit_pct?: number | null
  ambiguity_status?: string | null
  family_competitors?: string[]
  evaluated_family_competitors?: string[]
  gate_passed_family_competitors?: string[]
  best_family_market_by_edge?: string | null
  second_best_family_market_by_edge?: string | null
  selected_edge?: number | null
  best_other_edge?: number | null
  edge_gap_or_deficit?: number | null
  market_rows?: CecchinoPurchasabilityV3FamilyMarketRow[]
  comparison_rows?: Array<{
    market_key?: string | null
    market_label?: string | null
    edge_pct?: number | null
    gate_status?: string | null
    is_leader?: boolean | null
    is_selected?: boolean | null
    gap_from_leader_pct?: number | null
    used_in_comparison?: boolean | null
  }>
  [key: string]: unknown
}

export type CecchinoPurchasabilityV3LinkedMarketContext = {
  linked_market_key?: string | null
  relationship?: string | null
  edge_pct?: number | null
  vantaggio_prob?: number | null
  rating?: number | null
  gate_status?: string | null
  used_in_score?: boolean
  diagnostic_only?: boolean
}

export type CecchinoPurchasabilityV3DependencyMeta = {
  rating_used_in_score?: boolean
  probability_advantage_used_as_weight?: boolean
  score_acquisto_used?: boolean
  historical_profile_used?: boolean
  linked_markets_used_in_score?: boolean
  fixed_scales_used?: boolean
  edge_used_in_value_score?: boolean
  edge_used_in_family_ambiguity_only_as_comparison?: boolean
  book_opposite_used_only_in_opposite_penalty?: boolean
  probability_cecchino_used_in_risk_and_divergence_only?: boolean
}

export type CecchinoPurchasabilityV3Item = {
  market_key: string
  market_label?: string | null
  market_family?: string | null
  period?: string | null
  line?: number | null
  status: CecchinoPurchasabilityV3Status
  calculation_quality?: 'full' | 'partial' | 'not_applicable' | string | null
  score: number | null
  raw_score?: number | null
  score_display?: string | null
  class?: CecchinoPurchasabilityV3Class | null
  gate_status?: CecchinoPurchasabilityV3GateStatus | null
  gate_reason_codes?: string[]
  gate?: CecchinoPurchasabilityV3Gate | null
  value_score?: number | null
  quality_start?: number | null
  quality_score?: number | null
  total_penalty?: number | null
  penalties?: Record<string, CecchinoPurchasabilityV3Penalty>
  family?: CecchinoPurchasabilityV3Family | null
  opposite_market_key?: string | null
  opposite_fair_probability?: number | null
  opposite_pressure_penalty?: number | null
  linked_market_context?: CecchinoPurchasabilityV3LinkedMarketContext | null
  input?: Record<string, number | string | boolean | null>
  formula_steps?: string[]
  reading_short?: string | null
  reading_detailed?: string | null
  historical_reason_codes?: string[]
  fair_book_audit?: Record<string, unknown> | null
  theoretical?: Record<string, unknown> | null
  strengths?: string[]
  risks?: string[]
  reason_codes?: string[]
  warnings?: string[]
  historical_profile_used?: boolean
  fixed_scales_used?: boolean
  current_operational_version?: boolean
  parallel_candidate?: boolean
  pre_match_only?: boolean
  formula_version?: string | null
  candidate_version?: string | null
  dependency_meta?: CecchinoPurchasabilityV3DependencyMeta | null
}

export type CecchinoPurchasabilityV3Snapshot = {
  snapshot_version: string
  contract_version?: string
  feature_version?: string
  candidate_version: string
  candidate_name?: string
  formula_version?: string
  audit_version?: string
  registry_status?: string | null
  status: 'ok' | 'partial' | 'unavailable' | string
  items: CecchinoPurchasabilityV3Item[]
  summary?: Record<string, unknown>
  full_candidate_payload_sha256?: string | null
  generated_at?: string | null
  source_snapshot_at?: string | null
  source_snapshot_verified?: boolean | null
  source_snapshot_before_kickoff?: boolean | null
  source_mode?: string | null
  pre_match_only?: boolean
  historical_profile_used?: boolean
  fixed_scales_used?: boolean
  current_operational_version?: boolean
  parallel_candidate?: boolean
  contains_post_match_fields?: boolean
  signals_integration?: boolean
  warnings?: string[]
}

// ============================================================================
// Acquistabilità V3.1 (shadow candidate)
// ============================================================================

export type CecchinoPurchasabilityV31ItemStatus =
  | 'score'
  | 'score_provisional'
  | 'gate_failed'
  | 'non_calculable'

export type CecchinoPurchasabilityV31SectionKey =
  | 'final_state'
  | 'gate'
  | 'quote_quality'
  | 'fair_book'
  | 'theoretical_value'
  | 'penalties'
  | 'family_ambiguity'
  | 'historical_reliability'
  | 'final_calculation'
  | 'comparison_with_v3'

export type CecchinoPurchasabilityV31ExplanationSection = {
  section_key: CecchinoPurchasabilityV31SectionKey
  title?: string | null
  description?: string | null
  formula_symbolic?: string | null
  formula_applied?: string[]
  inputs?: Record<string, unknown>
  result?: unknown
  warnings?: string[]
}

export type CecchinoPurchasabilityV31Explanation = {
  sections?: CecchinoPurchasabilityV31ExplanationSection[] | Record<string, CecchinoPurchasabilityV31ExplanationSection>
  final_state?: {
    status?: CecchinoPurchasabilityV31ItemStatus | null
    score?: number | null
    class?: string | null
    reason?: string | null
    reason_code?: string | null
  }
  gate?: {
    gate_status?: string | null
    gate_passed?: boolean | null
    reason?: string | null
    reason_code?: string | null
  }
  quote_quality?: {
    status?: string | null
    performance_type?: string | null
    reason?: string | null
  }
  fair_book?: {
    fair_book_probability?: number | null
    quota_book?: number | null
    margin_pct?: number | null
  }
  theoretical_value?: {
    theoretical_raw?: number | null
    edge_pct?: number | null
  }
  penalties?: {
    total_penalty?: number | null
    penalties_applied?: Array<{
      key?: string | null
      label?: string | null
      points?: number | null
    }>
  }
  family_ambiguity?: {
    status?: string | null
    is_leader?: boolean | null
    leader_market_key?: string | null
    gap_from_leader?: number | null
  }
  historical_reliability?: {
    factor?: number | null
    historical_multiplier?: number | null
    score?: number | null
    class?: string | null
    sample_size?: number | null
    selected_sample_size?: number | null
    min_sample?: number | null
    historical_evidence_quality?: string | null
    historical_reliability_score?: number | null
    historical_adjustment_points?: number | null
  }
  final_calculation?: {
    theoretical_raw?: number | null
    theoretical_raw_score?: number | null
    historical_factor?: number | null
    historical_multiplier?: number | null
    historical_adjustment_points?: number | null
    raw_result?: number | null
    raw_score_v31?: number | null
    score?: number | null
    rounding?: string | null
  }
  comparison_with_v3?: {
    v3_score?: number | null
    v31_score?: number | null
    delta?: number | null
    direction?: string | null
  }
  [key: string]: unknown
}

export type CecchinoPurchasabilityV31Item = {
  market_key: string
  market_label?: string | null
  label?: string | null
  market_family?: string | null
  period?: string | null
  line?: number | null
  status: CecchinoPurchasabilityV31ItemStatus
  score: number | null
  score_v31?: number | null
  raw_score?: number | null
  raw_score_v31?: number | null
  class?: string | null
  class_v31?: string | null
  reason?: string | null
  reason_code?: string | null
  gate_status?: string | null
  gate_passed?: boolean | null
  calculation_quality?: string | null
  theoretical_raw?: number | null
  theoretical_raw_score?: number | null
  historical_factor?: number | null
  historical_multiplier?: number | null
  historical_adjustment_points?: number | null
  historical?: {
    sample_size?: number | null
    selected_sample_size?: number | null
    min_sample?: number | null
    historical_multiplier?: number | null
    historical_evidence_quality?: string | null
    historical_reliability_score?: number | null
    [key: string]: unknown
  } | null
  formula_version?: string | null
  candidate_version?: string | null
  audit_version?: string | null
  input?: Record<string, unknown>
  explanation?: CecchinoPurchasabilityV31Explanation | null
  is_real_book_quote?: boolean | null
  derived_quote?: boolean | null
  total_penalty?: number | null
  warnings?: string[]
  reading_short?: string | null
  reading_detailed?: string | null
  reason_codes?: string[]
  gate_reason_codes?: string[]
  historical_reason_codes?: string[]
  gate?: Record<string, unknown> | null
  fair_book_audit?: Record<string, unknown> | null
  theoretical?: Record<string, unknown> | null
  formula_steps?: string[]
  dependency_meta?: unknown
  value_score?: number | null
  quality_score?: number | null
  [key: string]: unknown
}

export type CecchinoPurchasabilityV31Snapshot = {
  snapshot_version: string
  contract_version?: string
  feature_version?: string
  candidate_version: string
  candidate_name?: string
  formula_version?: string
  audit_version?: string
  registry_status?: string | null
  status: 'ok' | 'partial' | 'unavailable' | string
  items: CecchinoPurchasabilityV31Item[]
  summary?: Record<string, unknown>
  generated_at?: string | null
  source_snapshot_at?: string | null
  pre_match_only?: boolean
  warnings?: string[]
}

/** Indexer V3.1 per market_key. */
export function indexPurchasabilityV31ByMarketKey(
  snapshot: CecchinoPurchasabilityV31Snapshot | null | undefined,
): Record<string, CecchinoPurchasabilityV31Item> {
  const items = snapshot?.items
  if (!items?.length) return {}
  const map: Record<string, CecchinoPurchasabilityV31Item> = {}
  for (const it of items) {
    if (it?.market_key) map[it.market_key] = it
  }
  return map
}

// ============================================================================
// Acquistabilità V3.5 (live shadow experiment — structural V/D/S/Q + A/B/C/D)
// ============================================================================

export type CecchinoPurchasabilityV35SnapshotStatus = 'valid' | 'unavailable' | 'invalid'

export type CecchinoPurchasabilityV35CandidateKey = 'A' | 'B' | 'C' | 'D'

export type CecchinoPurchasabilityV35ItemStatus = 'score' | 'gate_failed' | 'not_calculable'

export type CecchinoPurchasabilityV35ComponentBlock = {
  component?: string
  score?: number | null
  status?: string | null
  expected_value?: number | null
  delta_logit?: number | null
  raw_score?: number | null
  structural_confidence?: number | null
  coverage?: number | null
  configured_relation_count?: number | null
  available_relation_count?: number | null
  structural_status?: string | null
  overround_penalty?: number | null
  fallback_penalty?: number | null
  derived_fair_penalty?: number | null
  extreme_divergence_penalty?: number | null
  relations?: CecchinoPurchasabilityV35StructuralRelation[]
}

export type CecchinoPurchasabilityV35StructuralRelation = {
  related_market?: string | null
  support_score?: number | null
  related_delta_logit?: number | null
  relation_weight?: number | null
  relation_type?: string | null
  used_in_score?: boolean | null
  data_available?: boolean | null
}

export type CecchinoPurchasabilityV35Candidate = {
  candidate_id?: string | null
  candidate_name?: string | null
  raw_score?: number | null
  score?: number | null
  class?: string | null
  effective_weights?: Record<string, number | null>
  configured_weights?: Record<string, number | null>
  missing_components?: string[]
}

export type CecchinoPurchasabilityV35Gate = {
  gate_status?: string | null
  gate_passed?: boolean | null
  reason?: string | null
  reason_codes?: string[]
  expected_value?: number | null
  probability_cecchino?: number | null
  fair_book_probability?: number | null
  rating?: number | null
}

export type CecchinoPurchasabilityV35ItemInput = {
  execution_quote_real?: number | null
  execution_quote_source?: string | null
  probability_cecchino?: number | null
  fair_book_probability?: number | null
  rating?: number | null
  overround?: number | null
  book_fallback_used?: boolean | null
  fair_probability_may_be_derived?: boolean | null
}

export type CecchinoPurchasabilityV35Item = {
  market_key: string
  label?: string | null
  status: CecchinoPurchasabilityV35ItemStatus | string
  gate_status?: string | null
  gate?: CecchinoPurchasabilityV35Gate | null
  input?: CecchinoPurchasabilityV35ItemInput | null
  components?: {
    executable_value?: CecchinoPurchasabilityV35ComponentBlock | null
    market_disagreement?: CecchinoPurchasabilityV35ComponentBlock | null
    structural_coherence?: CecchinoPurchasabilityV35ComponentBlock | null
    information_quality?: CecchinoPurchasabilityV35ComponentBlock | null
  } | null
  candidates?: Partial<Record<CecchinoPurchasabilityV35CandidateKey, CecchinoPurchasabilityV35Candidate>>
  diagnostics?: Record<string, unknown> | null
  dependency_meta?: Record<string, unknown> | null
}

export type CecchinoPurchasabilityV35CandidateRegistryEntry = {
  id?: string | null
  name?: string | null
  weights?: Record<string, number | null>
}

export type CecchinoPurchasabilityV35Snapshot = {
  snapshot_version?: string | null
  contract_version?: string | null
  feature_version?: string | null
  formula_version?: string | null
  relation_registry_version?: string | null
  candidate_registry_version?: string | null
  registry_status?: string | null
  experiment_version?: string | null
  generated_at?: string | null
  source_snapshot_at?: string | null
  source_snapshot_verified?: boolean | null
  source_snapshot_before_kickoff?: boolean | null
  pre_match_verified?: boolean | null
  kickoff?: string | null
  source_mode?: string | null
  input_fingerprint_sha256?: string | null
  engine_payload_sha256?: string | null
  frozen_config?: {
    candidates?: Partial<
      Record<CecchinoPurchasabilityV35CandidateKey, CecchinoPurchasabilityV35CandidateRegistryEntry>
    >
    rating_min_gate?: number | null
    class_thresholds?: number[]
  } | null
  candidate_registry?: Partial<
    Record<CecchinoPurchasabilityV35CandidateKey, CecchinoPurchasabilityV35CandidateRegistryEntry>
  >
  relation_registry?: unknown[]
  items: CecchinoPurchasabilityV35Item[]
  summary?: Partial<
    Record<
      CecchinoPurchasabilityV35CandidateKey,
      {
        top_market_key?: string | null
        top_score?: number | null
        score_band_counts?: Record<string, number>
      }
    >
  >
  pre_match_only?: boolean
  historical_reliability_integrated?: boolean
  shadow_candidate?: boolean
  warnings?: string[]
}

/** Indexer V3.5 per market_key. */
export function indexPurchasabilityV35ByMarketKey(
  snapshot: CecchinoPurchasabilityV35Snapshot | null | undefined,
): Record<string, CecchinoPurchasabilityV35Item> {
  const items = snapshot?.items
  if (!items?.length) return {}
  const map: Record<string, CecchinoPurchasabilityV35Item> = {}
  for (const it of items) {
    if (it?.market_key) map[it.market_key] = it
  }
  return map
}

/** Indexer V3 per market_key — analogo ai resolver V1.1/V2 del DetailPanel. */
export function indexPurchasabilityV3ByMarketKey(
  snapshot: CecchinoPurchasabilityV3Snapshot | null | undefined,
): Record<string, CecchinoPurchasabilityV3Item> {
  const items = snapshot?.items
  if (!items?.length) return {}
  const map: Record<string, CecchinoPurchasabilityV3Item> = {}
  for (const it of items) {
    if (it?.market_key) map[it.market_key] = it
  }
  return map
}

export type CecchinoBetfairRefreshResponse = {
  status: string
  today_fixture_id?: number
  provider_fixture_id?: number
  bookmaker?: CecchinoOddsMeta & {
    name?: string
    provider_bookmaker_id?: number
    provider_source?: string
  }
  before?: Record<string, unknown>
  after?: Record<string, unknown>
  changed?: boolean
  changed_markets?: string[]
  kpi_panel?: CecchinoKpiV2Panel
  api_calls_used?: number
  manual_comparison_note?: { message?: string }
  warnings?: string[]
  message?: string
  code?: string
}

export type CecchinoBetfairMarketsJsonResponse = {
  status: string
  fixture?: Record<string, unknown>
  bookmaker?: CecchinoOddsMeta & { name?: string; provider_bookmaker_id?: number }
  odds_fetched_at?: string | null
  last_betfair_refresh_at?: string | null
  is_cached?: boolean | null
  api_calls_used?: number
  markets?: Array<Record<string, unknown>>
  raw_payload?: Record<string, unknown>
  manual_comparison_note?: { message?: string }
  warnings?: string[]
  message?: string
}

export type CecchinoPicchettiWeightsBlock = Record<string, number | string>

export type CecchinoPicchettiDebugWeights = {
  '1x2'?: CecchinoPicchettiWeightsBlock
  goal_markets?: CecchinoPicchettiWeightsBlock
}

export type CecchinoPicchettiDebugSummary = {
  version?: string
  formula_status?: string
  weights?: CecchinoPicchettiDebugWeights | Record<string, number>
  missing_formulas_count?: number
}

export const CECCHINO_1X2_WEIGHT_KEYS = [
  'totals',
  'home_away',
  'last6_totals',
  'last5_home_away',
] as const

export const CECCHINO_GOAL_WEIGHT_KEYS = [
  'totals',
  'home_away',
  'last6_totals',
  'last5_home_away',
] as const

const DEFAULT_1X2_WEIGHTS: Record<string, number> = {
  totals: 0.3,
  home_away: 0.3,
  last6_totals: 0.2,
  last5_home_away: 0.2,
}

const DEFAULT_GOAL_WEIGHTS: Record<string, number> = {
  totals: 0.2,
  home_away: 0.3,
  last6_totals: 0.2,
  last5_home_away: 0.3,
}

export function extract1x2Weights(
  weights?: CecchinoPicchettiDebugWeights | Record<string, number> | null,
): Record<string, number> {
  if (!weights) return DEFAULT_1X2_WEIGHTS
  if ('1x2' in weights && weights['1x2'] && typeof weights['1x2'] === 'object') {
    const block = weights['1x2'] as CecchinoPicchettiWeightsBlock
    const out: Record<string, number> = {}
    for (const key of CECCHINO_1X2_WEIGHT_KEYS) {
      const v = block[key]
      if (typeof v === 'number') out[key] = v
    }
    return Object.keys(out).length ? out : DEFAULT_1X2_WEIGHTS
  }
  const flat = weights as Record<string, number>
  if (typeof flat.totals === 'number') return flat
  return DEFAULT_1X2_WEIGHTS
}

export function extractGoalWeights(
  weights?: Record<string, number> | CecchinoPicchettiWeightsBlock | null,
): Record<string, number> {
  if (!weights) return DEFAULT_GOAL_WEIGHTS
  const out: Record<string, number> = {}
  for (const key of CECCHINO_GOAL_WEIGHT_KEYS) {
    const v = weights[key]
    if (typeof v === 'number') out[key] = v
  }
  return Object.keys(out).length ? out : DEFAULT_GOAL_WEIGHTS
}

export function formatWeightPct(value: number): string {
  return `${(value * 100).toFixed(0)}%`
}

export type CecchinoPicchettoContribution = {
  name: string
  weight: number
  sample_home?: number | null
  sample_away?: number | null
  record_home?: string
  record_away?: string
  probability?: number | null
  probability_pct?: number | null
  odd?: number | null
  weighted_contribution?: number | null
  status?: string
}

export type CecchinoGoalOuBlockDebug = {
  home_goals_for?: number
  away_goals_against?: number
  divisor_home?: number
  divisor_away?: number
  divisor?: number
  home_component?: number
  away_component?: number
  block_value?: number
  home_coeff?: number
  away_coeff?: number
  [key: string]: number | undefined
}

export type CecchinoGoalPtSideDebug = {
  sample?: number
  hits?: number
  rate?: number | null
}

export type CecchinoGoalMarketSummary = {
  lambda?: number
  poisson_probability?: number
  empirical_probability?: number
  league_event_probability?: number | null
  final_probability_raw?: number
  final_probability_capped?: number
  final_probability?: number
  final_odd?: number | null
  overall_reliability?: number
  reliability_badge?: string
}

export type CecchinoGoalMarketContextRow = {
  name?: string
  label?: string
  weight?: number
  original_weight?: number
  effective_weight?: number
  weight_renormalized?: boolean
  sample_home?: number
  sample_away?: number
  lambda_total?: number
  hit_rate_home?: number | null
  hit_rate_away?: number | null
  empirical_probability?: number | null
  reliability?: number
  status?: string
}

export type CecchinoGoalLegacyExcelParity = {
  final_odd?: number | null
  enabled_for_kpi?: boolean
}

export type CecchinoPicchettiMarketDebug = {
  market_key: string
  segno: string
  picchetti?: CecchinoPicchettoContribution[]
  final_odd?: number | null
  formula?: string
  inputs?: Record<string, number | null>
  formula_status?: string
  formula_version?: string
  formula_note?: string
  blocks?: {
    home_away?: CecchinoGoalOuBlockDebug
    totals?: CecchinoGoalOuBlockDebug
    mixed?: CecchinoGoalOuBlockDebug
  }
  event?: string
  home?: CecchinoGoalPtSideDebug
  away?: CecchinoGoalPtSideDebug
  probability?: number | null
  status?: string
  warnings?: string[]
  skipped_missing_halftime_score?: number
  summary?: CecchinoGoalMarketSummary
  weights?: Record<string, number>
  contexts?: CecchinoGoalMarketContextRow[]
  legacy_excel_parity?: CecchinoGoalLegacyExcelParity
  technical?: Record<string, unknown>
}

export type CecchinoPicchettiDebugResponse = {
  status: string
  version?: string
  formula_status?: string
  weights?: CecchinoPicchettiDebugWeights | Record<string, number>
  markets?: Record<string, CecchinoPicchettiMarketDebug>
  missing_formulas?: Array<{ market_key: string; label: string; formula_status: string }>
  warnings?: string[]
  fixture?: Record<string, unknown>
  final?: Record<string, unknown>
  message?: string
}

export type CecchinoBookmakerOddsDetailRow = {
  market_key: string
  label: string
  quota_betfair: number | null
  source: string
  status: string
}

export type CecchinoBookmakerOddsDetail = {
  rows: CecchinoBookmakerOddsDetailRow[]
}

export type CecchinoBalanceAnalysisF36 = {
  signed?: number
  abs?: number
  score?: number
  label?: string
  class_key?: string
  direction_note?: string
}

export type CecchinoBalanceAnalysisDominance = {
  value?: number
  best_side?: string
  best_side_label?: string
  best_probability?: number
  second_side?: string
  second_side_label?: string
  second_probability?: number
}

export type CecchinoBalanceAnalysisDominanceContext = {
  best_side?: string
  best_side_label?: string
  best_probability?: number
  second_side?: string
  second_side_label?: string
  second_probability?: number
  dominance_value?: number
  dominance_direction?: string
  label?: string
  interpretation?: string
  effect_on_balance?: string
}

export type CecchinoBalanceAnalysisSideGap = {
  value?: number
  label?: string
  class_key?: string
}

export type CecchinoBalanceAnalysisDraw = {
  quota_x?: number
  label?: string
  class_key?: string
}

export type CecchinoBalanceAnalysisCrossReading = {
  label?: string
  description?: string
}

export type CecchinoBalanceAnalysisOperational = {
  label?: string
  detail?: string
  class_key?: string
  severity?: 'positive' | 'warning' | 'negative' | 'neutral' | string
}

export type CecchinoIcmDriver = {
  key?: string
  symbol?: string
  status?: 'support' | 'partial' | 'conflict' | string
  plain_text?: string
}

export type CecchinoIcmNarrative = {
  key?: string
  label?: string
  description?: string
}

export type CecchinoIcmComposition = {
  key?: string
  label?: string
  source?: string
  plain_text?: string
}

export type CecchinoIcmCandidateNarrative = {
  key?: string
  label?: string
  score?: number
}

export type CecchinoIcmTechnical = {
  best_narrative?: string
  best_score?: number
  second_score?: number
  gap?: number
  ambiguity_penalty?: number
  final_score?: number
  driver_weights?: Record<string, number>
  forced_contradictory?: boolean
  driver_statuses_by_narrative?: Record<string, Record<string, string>>
}

export type CecchinoIcmAnalysis = {
  version?: string
  status?: string
  score?: number | null
  score_pct?: number | null
  class_key?: string | null
  label?: string
  short_label?: string | null
  severity?: 'positive' | 'warning' | 'negative' | 'neutral' | string | null
  dominant_narrative?: CecchinoIcmNarrative | null
  drivers?: CecchinoIcmDriver[]
  composition?: CecchinoIcmComposition[]
  candidate_narratives?: CecchinoIcmCandidateNarrative[]
  technical?: CecchinoIcmTechnical | null
  warnings?: string[]
}

export type CecchinoBalanceAnalysisSummary = {
  main_label?: string
  short_advice?: string
  favorite_direction?: string
  is_draw_under_candidate?: boolean
  is_false_balance?: boolean
  is_confirmed_imbalance?: boolean
  is_x_dominance?: boolean
}

export type CecchinoBalanceAnalysisTechnical = {
  f36_formula?: string
  dominance_formula?: string
  side_gap_formula?: string
  rule_id?: number
  operational_class_key?: string
  effect_on_balance?: string
  dominance_direction?: string
  x_dominance_note?: string
  lateral_dominance_note?: string
  legend_version?: string
}

export type CecchinoGoalIntensityThreshold = {
  line?: number
  active?: boolean
  label?: string
  probability?: number | null
}

export type CecchinoGoalIntensityAnalysis = {
  version?: string
  status?: string
  method?: string
  expected_goals_total?: number | null
  thresholds?: Record<string, CecchinoGoalIntensityThreshold> | null
  active_thresholds_count?: number | null
  final_class_key?: string | null
  final_label?: string | null
  plain_summary?: string | null
  debug?: {
    source?: string
    classification_method?: string
    note?: string
  }
  warnings?: string[]
}

export type CecchinoExpectedGoalEngineVariable = {
  key?: string
  label?: string
  block?: string
  weight?: number | null
  required?: boolean
  role?: string
  available?: boolean
  availability_status?: string
  value?: number | null
  normalized_value?: number | null
  source?: string | null
  source_field?: string | null
  sample_size?: number | null
  scope?: string
  period?: string
  description?: string
  warnings?: string[]
  note?: string
  anti_leakage?: {
    current_fixture_excluded?: boolean
    fixture_date_cutoff?: string | null
    scope?: string
  }
}

export type CecchinoExpectedGoalEngineCoverage = {
  required_available?: number
  required_total?: number
  advanced_available?: number
  advanced_total?: number
  coverage_pct?: number
  engine_ready?: boolean
  confidence?: string
}

export type CecchinoExpectedGoalEngineReadiness = {
  production_goal_ready?: boolean
  temporal_distribution_ready?: boolean
  advanced_correctors_ready?: string
  can_compute_expected_goals_ft?: boolean
  can_compute_expected_goals_ht?: boolean
  can_compute_home_away_expected_goals?: boolean
  can_compute_over_probabilities?: boolean
  can_compute_gg_ng?: boolean
  can_compute_scorelines?: boolean
  missing_critical_fields?: string[]
}

export type CecchinoExpectedGoalEngineDiagnostics = {
  version?: string
  status?: string
  fixture_id?: number | null
  coverage?: CecchinoExpectedGoalEngineCoverage | null
  engine_readiness?: CecchinoExpectedGoalEngineReadiness | null
  blocks?: {
    production_goal?: CecchinoExpectedGoalEngineVariable[]
    temporal_distribution?: CecchinoExpectedGoalEngineVariable[]
    advanced_correctors?: CecchinoExpectedGoalEngineVariable[]
  } | null
  xg_profiles?: {
    home_team?: Record<string, unknown> | null
    away_team?: Record<string, unknown> | null
    anti_leakage?: Record<string, unknown> | null
  } | null
  xg_api_usage?: {
    automatic?: boolean
    external_calls_made?: number
    cache_hits?: number
    fixtures_checked?: number
    fixtures_backfilled?: number
    endpoint?: string
  } | null
  warnings?: string[]
}

export type CecchinoBackfillCurrentSeasonXgResponse = {
  status?: string
  today_fixture_id?: number
  xg_profiles?: Record<string, unknown>
  xg_api_usage?: Record<string, unknown>
  warnings?: string[]
  message?: string
}

export type CecchinoApiRawInspectorTeam = {
  id?: number | string | null
  name?: string | null
  side?: string | null
}

export type CecchinoApiRawInspectorMatch = {
  endpoint?: string
  source?: string
  path?: string
  key?: string
  matched_keyword?: string
  type?: string | number | null
  value?: string | number | null
  team?: CecchinoApiRawInspectorTeam | null
  raw_item?: unknown
}

export type CecchinoApiRawInspectorSource = {
  key?: string
  label?: string
  available?: boolean
  origin?: string
  records_count?: number
  called?: boolean
}

export type CecchinoApiRawInspectorXgField = {
  value?: number | null
  source?: string | null
  source_field?: string | null
  confidence?: string
  note?: string
}

export type CecchinoApiRawInspectorSuggestedMapping = {
  status?: string
  warnings?: string[]
  home_xg_for?: CecchinoApiRawInspectorXgField
  away_xg_for?: CecchinoApiRawInspectorXgField
  home_xg_against?: CecchinoApiRawInspectorXgField
  away_xg_against?: CecchinoApiRawInspectorXgField
}

export type CecchinoApiRawInspectorResponse = {
  version?: string
  status?: string
  fixture?: {
    today_fixture_id?: number
    provider_fixture_id?: number | null
    match?: string
    league?: string | null
    season?: number | null
    home_team?: string | null
    away_team?: string | null
  }
  ids?: {
    today_fixture_id?: number
    fixture_id?: number | null
    provider_fixture_id?: number | null
    league_id?: number | null
    provider_league_id?: number | null
    season?: number | null
    home_team_id?: number | null
    provider_home_team_id?: number | null
    away_team_id?: number | null
    provider_away_team_id?: number | null
  }
  api_usage?: {
    force_refresh?: boolean
    external_calls_made?: number
    endpoints_called?: string[]
    note?: string
  }
  searched_keywords?: string[]
  sources_checked?: CecchinoApiRawInspectorSource[]
  matches_found?: CecchinoApiRawInspectorMatch[]
  suggested_xg_mapping?: CecchinoApiRawInspectorSuggestedMapping
  raw_payloads?: Record<string, unknown>
  warnings?: string[]
}

export type CecchinoBalanceAnalysis = {
  version?: string
  status?: string
  inputs?: {
    quota_1?: number
    quota_x?: number
    quota_2?: number
    prob_1?: number
    prob_x?: number
    prob_2?: number
  }
  f36?: CecchinoBalanceAnalysisF36
  side_probability_gap?: CecchinoBalanceAnalysisSideGap
  dominance?: CecchinoBalanceAnalysisDominance
  dominance_context?: CecchinoBalanceAnalysisDominanceContext
  draw?: CecchinoBalanceAnalysisDraw
  cross_reading?: CecchinoBalanceAnalysisCrossReading
  operational?: CecchinoBalanceAnalysisOperational
  summary?: CecchinoBalanceAnalysisSummary
  technical?: CecchinoBalanceAnalysisTechnical
  warnings?: string[]
}

export type CecchinoBalanceV5Component = {
  key: string
  label: string
  value: number | string | null
  unit: string
  status: string
}

export type CecchinoBalanceV5Pillar = {
  key: string
  title: string
  question: string
  status: 'official' | 'descriptive_official' | 'unavailable' | string
  version?: string
  index: number | null
  class_label: string | null
  class_key?: string | null
  reading: string
  direction?: string | null
  calculation_quality?: string | null
  components?: CecchinoBalanceV5Component[]
  warnings?: string[]
  informational_note?: string | null
  /** V3 — F36 base puro (prima della correzione Quota Media X) */
  base_index?: number | null
  base_class_label?: string | null
  base_class_key?: string | null
  f36_signed?: number | null
  f36_abs?: number | null
  quota_x_book?: number | null
  quota_x_cecchino?: number | null
  quota_x_media?: number | null
  x_mean_threshold?: number | null
  x_mean_delta?: number | null
  x_mean_strength?: number | null
  x_mean_direction?: string | null
  x_mean_adjustment?: number | null
  x_mean_source_status?: string | null
  x_mean_book_source?: string | null
  x_mean_book_real?: boolean | null
  adjusted_index_raw?: number | null
  adjusted_index?: number | null
  adjusted_class_label?: string | null
  adjusted_class_key?: string | null
}

export type CecchinoBalanceV5MarketPair = {
  key: string
  label: string
  quota_cecchino?: number | null
  quota_book?: number | null
  prob_cecchino_norm?: number | null
  prob_book_norm?: number | null
  prob_cecchino_pct?: number | null
  prob_book_pct?: number | null
  signed_diff?: number | null
  abs_diff?: number | null
  signed_diff_pp?: number | null
  abs_diff_pp?: number | null
  deviation_pp?: number | null
  direction_label?: string | null
  direction?: string | null
}

export type CecchinoBalanceV5MarketDeviation = {
  title?: string
  subtitle?: string
  status: string
  index?: number | null
  class_label?: string | null
  pairs: CecchinoBalanceV5MarketPair[]
  reading: string
  warnings?: string[]
  has_book_data?: boolean
}

export type CecchinoBalanceV5 = {
  status?: 'ok' | 'unavailable' | string
  version: string
  inputs?: Record<string, unknown>
  pillars: Record<string, CecchinoBalanceV5Pillar> | CecchinoBalanceV5Pillar[]
  pillar_order?: string[]
  market_deviation: CecchinoBalanceV5MarketDeviation
  structural_summary?: string
  warnings?: string[]
}

export type CecchinoFixtureIdentityConsistency = {
  status: 'consistent' | 'inconsistent' | 'unavailable' | string
  today_fixture_id?: number
  local_fixture_id?: number | null
  provider_fixture_id?: number
  local_api_fixture_id?: number
  raw_sources?: {
    today?: Record<string, unknown> | null
    local_fixture?: Record<string, unknown> | null
    calculation_snapshot?: Record<string, unknown> | null
  }
  today_kickoff?: string | null
  local_fixture_kickoff?: string | null
  calculation_target_kickoff?: string | null
  xg_cutoff?: string | null
  provider_match?: boolean
  teams_match?: boolean
  competition_match?: boolean
  kickoff_match?: boolean
  status_match?: boolean
  score_match?: boolean
  snapshot_match?: boolean
  chronological_status_valid?: boolean
  verification_mode?: 'current_strict' | 'historical_snapshot' | string
  historical_identity_status?: string | null
  status_match_blocking?: boolean
  score_match_blocking?: boolean
  static_identity_verified?: boolean
  warnings?: string[]
}

export type CecchinoBalanceV5SnapshotMeta = {
  mode?: 'current_strict' | 'historical_snapshot' | string
  status?: 'verified' | 'partial' | 'blocked' | string
  source?: string
  scan_date?: string | null
  kickoff?: string | null
  calculation_target_kickoff?: string | null
  odds_fetched_at?: string | null
  static_identity_verified?: boolean
  status_match_blocking?: boolean
  score_match_blocking?: boolean
  book_snapshot_status?: 'verified' | 'partial' | 'unavailable' | 'blocked' | string
  warnings?: string[]
}

export type CecchinoTodayFixtureIds = {
  today_fixture_id: number
  local_fixture_id: number | null
  provider_fixture_id: number
}

export type CecchinoTodayDetailResponse = {
  status: string
  version?: string
  id?: number
  today_fixture_id?: number
  scan_date?: string
  provider_source?: string
  provider_fixture_id?: number
  local_fixture_id?: number | null
  fixture_ids?: CecchinoTodayFixtureIds
  competition_id?: number | null
  country_name?: string | null
  league_name?: string | null
  home_team_name?: string | null
  away_team_name?: string | null
  kickoff?: string | null
  fixture_status?: string | null
  odds_snapshot?: Record<string, unknown>
  stats_snapshot?: Record<string, unknown>
  cecchino_output?: Record<string, unknown>
  signals_matrix?: Record<string, unknown>
  signal_contract?: {
    formula_version?: string
    formula_label?: string
    consensus_policy_version?: string
    audit_version?: string
    decimal_policy?: {
      scope?: string
      quantum?: string
      rounding?: string
    }
    operational_signal_semantics?: string
    operational_semantics?: string
    legacy_versions_operational?: boolean
    is_current_formula?: boolean
    matrix_status?: string | null
    detected_formula_version?: string | null
    reason_code?: string | null
  }
  kpi_panel?: CecchinoKpiV2Panel
  kpi_panel_v2?: CecchinoKpiV2Panel
  picchetti_debug_summary?: CecchinoPicchettiDebugSummary
  icm_analysis?: CecchinoIcmAnalysis
  balance_analysis?: CecchinoBalanceAnalysis
  balance_v5?: CecchinoBalanceV5
  balance_v5_snapshot_meta?: CecchinoBalanceV5SnapshotMeta
  fixture_identity_consistency?: CecchinoFixtureIdentityConsistency
  goal_intensity_analysis?: CecchinoGoalIntensityAnalysis
  goal_intensity_v5?: {
    status: string
    banner?: string
    error?: string
    message?: string
    version?: string
    module_version?: string
    bundle_version?: string
    operational_status?: string
    operational_status_label_it?: string
    role?: string
    signals_integration_status?: string
    source?: string
    presentation?: string
    legacy_archive?: boolean
    index?: { id?: string; score?: number | null } | null
    outputs?: Record<string, unknown>
    data_quality?: Record<string, unknown>
    fallback?: Record<string, unknown> | null
    calibrated_predictions?: Record<string, unknown>
    primary_candidate_score?: number | null
    bundle?: Record<string, unknown>
    snapshot?: Record<string, unknown>
    v4_unchanged?: boolean
    no_betting_signals?: boolean
  }
  /** @deprecated Usa goal_intensity_v5 */
  goal_intensity_v5_preview?: {
    status: string
    banner?: string
    error?: string
    message?: string
    version?: string
    bundle?: Record<string, unknown>
    snapshot?: Record<string, unknown>
    v4_unchanged?: boolean
    no_betting_signals?: boolean
  }
  expected_goal_engine_diagnostics?: CecchinoExpectedGoalEngineDiagnostics
  purchasability_preview?: CecchinoPurchasabilityPreviewSnapshot | null
  purchasability_preview_v2?: CecchinoPurchasabilityPreviewSnapshot | null
  purchasability_preview_v3?: CecchinoPurchasabilityV3Snapshot | null
  purchasability_preview_v31?: CecchinoPurchasabilityV31Snapshot | null
  purchasability_preview_v35?: CecchinoPurchasabilityV35Snapshot | null
  purchasability_v35_snapshot_status?: CecchinoPurchasabilityV35SnapshotStatus | null
  purchasability_v35_snapshot_reason?: string | null
  purchasability_observational_v1_1?: Record<
    string,
    CecchinoPurchasabilityObservationalItem
  > | null
  purchasability_observational_v2?: Record<
    string,
    CecchinoPurchasabilityObservationalItem
  > | null
  purchasability_comparison?: CecchinoPurchasabilityComparison | null
  bookmaker_odds_detail?: CecchinoBookmakerOddsDetail
  cecchino_link?: string | null
  warnings?: string[]
  code?: string
  message?: string
}

export type CecchinoTodayExcludedFixture = {
  id: number
  provider_fixture_id: number
  home_team_name: string | null
  away_team_name: string | null
  league_name: string | null
  country_name: string | null
  kickoff: string | null
  eligibility_status: string
  eligibility_reason: string | null
  blocking_reasons?: string[]
  bookmaker_debug: Record<string, string>
  stats_debug: Record<string, unknown>
  cecchino_debug?: CecchinoTodayCecchinoDebug
  kpi_debug?: CecchinoTodayKpiDebug
  import_info?: string[]
  competition_filter_debug: Record<string, unknown>
  fixture_status_debug?: Record<string, unknown>
  api_usage_debug?: Record<string, unknown>
  warnings: string[]
}

export type CecchinoTodayCecchinoDebug = {
  missing_picchetto_quotas?: string[]
  zero_probability?: string[]
  final_odds_status?: string | null
  missing_final_odds?: string[]
}

export type CecchinoTodayKpiDebug = {
  kpi_status?: string
  missing_rows?: string[]
}

export type CecchinoTodayRevalidateDayResponse = {
  status: string
  version: string
  date: string
  checked: number
  kept_eligible: number
  moved_to_excluded: number
  reasons: Record<string, number>
}

export type CecchinoTodayExcludedResponse = {
  status: string
  version: string
  scan_date: string
  total: number
  fixtures: CecchinoTodayExcludedFixture[]
  scan_meta?: CecchinoTodayScanMeta
}

export type CecchinoTodayDebugSearchResponse = {
  status: string
  scan_date: string
  query?: string
  match_type?: string
  message?: string
  results: Array<{
    match_type: string
    fixture: Record<string, unknown>
    message: string
  }>
}

function qs(params: Record<string, string | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') p.set(k, v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function todayIsoRome(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(new Date())
}

export function formatDayShort(dateIso: string): string {
  const [, m, d] = dateIso.split('-')
  return `${d}/${m}`
}

export async function startCecchinoTodayScanDay(params: {
  date: string
  timezone?: string
  forceRescan?: boolean
}): Promise<CecchinoTodayScanJobStartResponse> {
  return adminPostJson<CecchinoTodayScanJobStartResponse>(
    '/api/admin/cecchino/today/scan-day/start',
    {
      date: params.date,
      timezone: params.timezone ?? 'Europe/Rome',
      force_rescan: params.forceRescan ?? false,
    },
    { timeoutMs: 15_000 },
  )
}

export async function getCecchinoTodayScanJob(jobId: string): Promise<CecchinoTodayScanJob> {
  return adminGetJson<CecchinoTodayScanJob>(`/api/admin/cecchino/today/scan-jobs/${jobId}`)
}

export async function getCecchinoTodayLatestScanJob(
  date: string,
): Promise<CecchinoTodayScanJob | null> {
  return adminGetJson<CecchinoTodayScanJob | null>(
    `/api/admin/cecchino/today/scan-jobs/latest?date=${encodeURIComponent(date)}`,
  )
}

/** @deprecated Usare startCecchinoTodayScanDay + polling job */
export async function scanCecchinoTodayDay(params: {
  date: string
  timezone?: string
  forceRescan?: boolean
}): Promise<CecchinoTodayScanJobStartResponse> {
  return startCecchinoTodayScanDay(params)
}

export async function updateCecchinoTodayResults(params: {
  date: string
  timezone?: string
}): Promise<CecchinoTodayUpdateResultsResponse> {
  return adminPostJson<CecchinoTodayUpdateResultsResponse>('/api/admin/cecchino/today/update-results', {
    date: params.date,
    timezone: params.timezone ?? 'Europe/Rome',
  })
}

export async function getCecchinoTodayDays(): Promise<CecchinoTodayDaysResponse> {
  return requestJson<CecchinoTodayDaysResponse>('/api/cecchino/today/days?timezone=Europe/Rome')
}

export async function getCecchinoTodayList(params: {
  date?: string
  country?: string
  league?: string
  timezone?: string
} = {}): Promise<CecchinoTodayListResponse> {
  return requestJson<CecchinoTodayListResponse>(
    `/api/cecchino/today${qs({
      date: params.date,
      country: params.country,
      league: params.league,
      timezone: params.timezone ?? 'Europe/Rome',
    })}`,
  )
}

export async function getCecchinoTodayDetail(todayFixtureId: number): Promise<CecchinoTodayDetailResponse> {
  return requestJson<CecchinoTodayDetailResponse>(`/api/cecchino/today/${todayFixtureId}`)
}

export type CecchinoKpiDebugJsonResponse = {
  status: string
  fixture?: {
    today_fixture_id: number
    local_fixture_id: number | null
    provider_fixture_id: number
    home_team: string | null
    away_team: string | null
    kickoff: string | null
  }
  bookmaker?: {
    provider_source: string
    provider_bookmaker_id: number
    name: string
  }
  kpi_panel?: CecchinoKpiV2Panel
  icm_analysis?: CecchinoIcmAnalysis
  balance_analysis?: CecchinoBalanceAnalysis
  betfair_odds_used?: Record<string, unknown>
  cecchino_odds_used?: Record<string, unknown>
  raw_betfair_markets_used?: Array<Record<string, unknown>>
  warnings?: string[]
  message?: string
}

export async function getCecchinoKpiDebugJson(
  todayFixtureId: number,
): Promise<CecchinoKpiDebugJsonResponse> {
  return requestJson<CecchinoKpiDebugJsonResponse>(
    `/api/cecchino/today/${todayFixtureId}/kpi-debug-json`,
  )
}

export type CecchinoKpiExplanationInput = {
  key: string
  label: string
  value: unknown
  display_value?: string
  source_path: string
  source_type?: string
  timestamp?: string | null
}

export type CecchinoKpiExplanationConsistency = {
  status: 'match' | 'rounding_match' | 'mismatch' | 'not_verifiable' | 'unavailable' | string
  delta?: number | null
}

export type CecchinoKpiExplanation = {
  module: string
  market_key: string
  market_label: string
  metric_key: string
  metric_label: string
  status: string
  calculation_type?: string
  description: string
  purpose: string
  formula_symbolic: string
  formula_applied: string[]
  inputs: CecchinoKpiExplanationInput[]
  stored_result: unknown
  stored_result_display?: string | null
  audit_result: unknown
  consistency: CecchinoKpiExplanationConsistency
  rounding?: {
    policy?: string
    precision?: number | null
    display_precision?: number | null
  }
  formula_version?: string
  warnings?: string[]
  unavailable_reason?: string
  [key: string]: unknown
}

export type CecchinoKpiExplanationsResponse = {
  status: string
  code?: string
  message?: string
  audit_version?: string
  no_model_recalculation?: boolean
  generated_at?: string
  fixture?: {
    today_fixture_id: number
    local_fixture_id?: number | null
    provider_fixture_id?: number | null
    home_team?: string | null
    away_team?: string | null
    kickoff?: string | null
    scan_date?: string | null
    competition_id?: number | null
  }
  panel_version?: string
  excluded_metrics?: string[]
  analyzable_metrics?: string[]
  markets: Record<string, Record<string, CecchinoKpiExplanation>>
  warnings?: string[]
  metadata?: Record<string, unknown>
}

export async function getKpiExplanations(
  todayFixtureId: number,
): Promise<CecchinoKpiExplanationsResponse> {
  return requestJson<CecchinoKpiExplanationsResponse>(
    `/api/cecchino/today/${todayFixtureId}/kpi-explanations`,
  )
}

export type CecchinoPurchasabilityAuditExport = {
  contract_version: string
  generated_at: string
  fixture: Record<string, unknown>
  source_versions: Record<string, string | null>
  market_order: string[]
  market_context: {
    BOOK: Record<string, unknown>
    CECCHINO: Record<string, unknown>
  }
  markets: Record<string, unknown>
}

export async function getPurchasabilityAuditExport(
  todayFixtureId: number,
): Promise<CecchinoPurchasabilityAuditExport> {
  return requestJson<CecchinoPurchasabilityAuditExport>(
    `/api/cecchino/today/${todayFixtureId}/purchasability-audit-export`,
  )
}

export async function downloadDailyPurchasabilityAuditExport(scanDate: string): Promise<Blob> {
  const base = getCecchinoApiBase()
  const url = `${base}/api/cecchino/today/purchasability-audit-export/daily?scan_date=${encodeURIComponent(scanDate)}`
  const res = await fetch(url)
  if (!res.ok) {
    let msg = res.statusText
    const ct = res.headers.get('content-type') ?? ''
    if (ct.includes('application/json')) {
      try {
        const parsed = (await res.json()) as { message?: string }
        if (parsed.message) msg = parsed.message
      } catch {
        /* ignore */
      }
    }
    throw new Error(msg)
  }
  return res.blob()
}

export function triggerDailyPurchasabilityAuditDownload(blob: Blob, scanDate: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `purchasability-audits-${scanDate}.zip`
  a.click()
  URL.revokeObjectURL(url)
}

export type CecchinoPurchasabilityV35AuditExport = {
  contract_version: string
  generated_at: string
  fixture: Record<string, unknown>
  snapshot_identity: Record<string, unknown>
  frozen_config: Record<string, unknown>
  candidate_registry: Record<string, unknown>
  relation_registry: unknown[]
  market_order: string[]
  markets: Record<string, unknown>
}

export async function getPurchasabilityV35AuditExport(
  todayFixtureId: number,
): Promise<CecchinoPurchasabilityV35AuditExport> {
  return requestJson<CecchinoPurchasabilityV35AuditExport>(
    `/api/cecchino/today/${todayFixtureId}/purchasability-v35-audit-export`,
  )
}

export async function downloadDailyPurchasabilityV35Audit(scanDate: string): Promise<Blob> {
  const base = getCecchinoApiBase()
  const url = `${base}/api/cecchino/today/purchasability-v35-audit-export/daily?scan_date=${encodeURIComponent(scanDate)}`
  const res = await fetch(url)
  if (!res.ok) {
    let msg = res.statusText
    const ct = res.headers.get('content-type') ?? ''
    if (ct.includes('application/json')) {
      try {
        const parsed = (await res.json()) as { message?: string }
        if (parsed.message) msg = parsed.message
      } catch {
        /* ignore */
      }
    }
    throw new Error(msg)
  }
  return res.blob()
}

export function triggerDailyPurchasabilityV35AuditDownload(blob: Blob, scanDate: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `purchasability-v35-audits-${scanDate}.zip`
  a.click()
  URL.revokeObjectURL(url)
}

export type CecchinoSignalConditionLeaf = {
  condition_key: string
  label: string
  left_label: string
  left_value: unknown
  left_display?: string
  operator: string
  right_label: string
  right_value: unknown
  right_display?: string
  expression: string
  passed: boolean
  source_path: string
}

export type CecchinoSignalLogicGroup = {
  operator: 'AND' | 'OR' | string
  group_key?: string
  label?: string
  conditions?: CecchinoSignalConditionLeaf[]
  branches?: CecchinoSignalLogicGroup[]
  result?: string
}

export type CecchinoSignalExplanationInput = {
  excel_name?: string
  key: string
  label: string
  value: unknown
  display_value?: string
  source_path: string
  source_type?: string
  derivation?: string
}

export type CecchinoSignalCellExplanation = {
  row_key: string
  row_label: string
  column_key: string
  column_label: string
  source_cell: string
  stored_result: string | null
  canonical_audit_result: string | null
  condition_trace_result: string | null
  consistency: { status: string; stored?: string | null; canonical?: string | null; trace?: string | null }
  description: string
  purpose: string
  target_market?: string
  excel_formula: string
  formula_symbolic: string
  formula_applied: string[]
  logic: CecchinoSignalLogicGroup
  passed_conditions: CecchinoSignalConditionLeaf[]
  failed_conditions: CecchinoSignalConditionLeaf[]
  reason_summary: string
  inputs: CecchinoSignalExplanationInput[]
  warnings?: string[]
  si_meaning?: string
  no_meaning?: string
}

export type CecchinoSignalExplanationsResponse = {
  status: string
  code?: string
  message?: string
  audit_version?: string
  module?: string
  generated_at?: string
  no_operational_recalculation?: boolean
  diagnostic_re_evaluation_only?: boolean
  fixture?: {
    today_fixture_id: number
    local_fixture_id?: number | null
    provider_fixture_id?: number | null
    home_team?: string | null
    away_team?: string | null
    kickoff?: string | null
    scan_date?: string | null
  }
  matrix?: {
    source?: string
    status?: string
    inputs?: Record<string, unknown>
    reliability?: Record<string, unknown>
    excel_mapping?: Record<string, unknown>
    warnings?: string[]
  }
  active_cell_count?: number
  excluded_cells?: string
  cells: Record<string, CecchinoSignalCellExplanation>
  warnings?: string[]
}

export async function getSignalExplanations(
  todayFixtureId: number,
): Promise<CecchinoSignalExplanationsResponse> {
  return requestJson<CecchinoSignalExplanationsResponse>(
    `/api/cecchino/today/${todayFixtureId}/signal-explanations`,
  )
}

export type CecchinoBalanceExplanationInput = {
  key: string
  label: string
  value: unknown
  display_value?: string
  source_path: string
  source_type?: string
  derivation?: string
}

export type CecchinoBalanceExplanationComponent = {
  key?: string
  label?: string
  value?: unknown
  unit?: string | null
  weight?: number | null
  contribution?: number | null
  source?: string | null
}

export type CecchinoBalanceClassificationTraceItem = {
  class: string
  condition: string
  matched: boolean
}

export type CecchinoBalancePillarExplanation = {
  pillar_key: string
  pillar_number: number
  title: string
  status: string
  classification_type?: string
  badge?: string
  question?: string
  description?: string
  purpose?: string
  interpretation?: string
  methodological_caution?: string
  formula_symbolic?: string
  formula_applied?: string[]
  inputs?: CecchinoBalanceExplanationInput[]
  components?: CecchinoBalanceExplanationComponent[]
  displayed_result?: {
    value?: number | null
    display_value?: string | null
    class?: string | null
    direction?: string | null
  }
  canonical_audit_result?: {
    value?: number | null
    class?: string | null
    direction?: string | null
    [key: string]: unknown
  }
  consistency?: {
    status: string
    delta?: number | null
  }
  classification_trace?: CecchinoBalanceClassificationTraceItem[]
  reason_summary?: string
  formula_version?: string
  source_paths?: string[]
  warnings?: string[]
}

export type CecchinoBalanceExplanationsResponse = {
  status: string
  code?: string
  message?: string
  audit_version?: string
  module?: string
  generated_at?: string
  no_operational_recalculation?: boolean
  diagnostic_re_evaluation_only?: boolean
  source_mode?: string
  fixture?: {
    today_fixture_id: number
    local_fixture_id?: number | null
    provider_fixture_id?: number | null
    home_team?: string | null
    away_team?: string | null
    kickoff?: string | null
    scan_date?: string | null
  }
  overview?: {
    version?: string
    pre_match_only?: boolean
    official_pillars?: string[]
    descriptive_pillars?: string[]
    canonical_pillar_order?: string[]
    audit_pillar_order?: string[]
  }
  pillars: Record<string, CecchinoBalancePillarExplanation>
  warnings?: string[]
  metadata?: Record<string, unknown>
}

export async function getBalanceExplanations(
  todayFixtureId: number,
): Promise<CecchinoBalanceExplanationsResponse> {
  return requestJson<CecchinoBalanceExplanationsResponse>(
    `/api/cecchino/today/${todayFixtureId}/balance-explanations`,
  )
}

export type CecchinoGiV5EcdfNormalization = {
  feature_key?: string
  train_n?: number | null
  train_min?: number | null
  train_max?: number | null
  train_median?: number | null
  quantiles?: Record<string, number | null>
  distribution_hash?: string | null
  normalization_method?: string
  tie_handling?: string
  clipping_rules?: string
  raw_value?: number | null
  clipped_value?: number | null
  clipping_applied?: boolean
  lower_count?: number | null
  equal_count?: number | null
  midrank?: number | null
  percentile_result?: number | null
  status?: string
}

export type CecchinoGiV5RawFeature = {
  key: string
  label: string
  value?: number | null
  source_path?: string
}

export type CecchinoGiV5DimensionMetric = {
  metric_key: string
  label: string
  description?: string | null
  formula_symbolic?: string
  formula_applied?: string[]
  raw_features?: CecchinoGiV5RawFeature[]
  normalization?: CecchinoGiV5EcdfNormalization | Record<string, CecchinoGiV5EcdfNormalization> | Record<string, unknown>
  stored_result?: number | null
  audit_result?: number | null
  consistency?: { status: string; delta?: number | null }
  used_by_candidates?: string[]
  warnings?: string[]
}

export type CecchinoGiV5DisplayTransformation = {
  key: string
  formula_symbolic?: string
  mathematical_value_key?: string
  mathematical_value?: number | null
  display_value?: number | null
  message?: string
  used_by_candidates?: boolean
}

export type CecchinoGiV5DimensionExplanation = {
  dimension_key: string
  dimension_number: number
  title: string
  status: string
  description?: string
  purpose?: string
  direction?: string
  metrics: CecchinoGiV5DimensionMetric[]
  display_transformations?: CecchinoGiV5DisplayTransformation[]
  mandatory_message?: string
  reason_summary?: string
  data_origin?: Record<string, unknown>
  warnings?: string[]
}

export type CecchinoGiV5CandidateComponent = {
  key: string
  label?: string
  role?: string
  value?: number | null
  contribution?: number | null
  weight?: number | null
}

export type CecchinoGiV5CalibrationBlock = {
  target?: string
  calibration_method?: string
  formula_symbolic?: string
  formula_applied?: string[]
  score?: number | null
  intercept?: number | null
  coefficient?: number | null
  product?: number | null
  z?: number | null
  raw_result?: number | null
  raw_probability?: number | null
  probability_percent?: number | null
  stored_result?: number | null
  audit_result?: number | null
  consistency?: { status: string; delta?: number | null }
  train_n?: number | null
  train_positive_rate?: number | null
  rounding?: string
}

export type CecchinoGiV5CandidateExplanation = {
  candidate_id: string
  role: string
  status: string
  description?: string
  purpose?: string
  research_status?: {
    preview_monitored?: boolean
    not_linked_to_signals?: boolean
    no_productive_formula?: boolean
    labels?: string[]
  }
  formula_symbolic?: string
  formula_applied?: string[]
  components?: CecchinoGiV5CandidateComponent[]
  excluded_components?: string[]
  weight_status?: string
  stored_score?: number | null
  audit_score?: number | null
  consistency?: { status: string; delta?: number | null }
  difference_vs_primary?: number | null
  calibrated_predictions?: {
    expected_total_goals?: CecchinoGiV5CalibrationBlock
    probability_goals_ge_2?: CecchinoGiV5CalibrationBlock
    probability_goals_ge_3?: CecchinoGiV5CalibrationBlock
    probability_btts?: CecchinoGiV5CalibrationBlock
  }
  reason_summary?: string
  quality?: Record<string, unknown>
  warnings?: string[]
}

export type CecchinoGiV5ExplanationsResponse = {
  status: string
  code?: string
  message?: string
  audit_version?: string
  module?: string
  module_version?: string
  presentation?: string
  consistency_status?: string
  generated_at?: string
  no_operational_recalculation?: boolean
  diagnostic_re_evaluation_only?: boolean
  source_mode?: string
  source_identity?: {
    today_fixture_id?: number
    snapshot_id?: number
    bundle_id?: number
    bundle_version?: string
    candidate_definition_hash?: string | null
  }
  fixture?: {
    today_fixture_id: number
    local_fixture_id?: number | null
    provider_fixture_id?: number | null
    home_team?: string | null
    away_team?: string | null
    kickoff?: string | null
    scan_date?: string | null
  }
  snapshot?: {
    snapshot_id?: number
    bundle_id?: number
    bundle_version?: string
    candidate_version?: string
    candidate_definition_hash?: string | null
    source_snapshot_at?: string | null
    bundle_frozen_at?: string | null
    snapshot_status?: string
    feature_status?: string | null
    freeze_check?: Record<string, boolean | null>
    reason_codes?: unknown
  }
  index?: Record<string, unknown>
  target_heads?: Record<string, Record<string, unknown>>
  /** Legacy preview dimensions; null/absent for official_support. */
  dimensions?: Record<string, CecchinoGiV5DimensionExplanation> | null
  /** Legacy candidates; null for official_support. */
  candidates?: Record<string, CecchinoGiV5CandidateExplanation> | null
  additional_candidates?: Record<string, unknown>
  archived_candidates_hidden?: boolean
  warnings?: string[]
  metadata?: Record<string, unknown>
}

export async function getGoalIntensityV5Explanations(
  todayFixtureId: number,
): Promise<CecchinoGiV5ExplanationsResponse> {
  return requestJson<CecchinoGiV5ExplanationsResponse>(
    `/api/cecchino/today/${todayFixtureId}/goal-intensity-v5-explanations`,
  )
}

export async function getPicchettiDebugJson(
  todayFixtureId: number,
): Promise<CecchinoPicchettiDebugResponse> {
  return requestJson<CecchinoPicchettiDebugResponse>(
    `/api/cecchino/today/${todayFixtureId}/picchetti-debug`,
  )
}

export async function getApiRawInspector(
  todayFixtureId: number,
  params: {
    forceRefresh?: boolean
    includeRaw?: boolean
    endpoints?: string
  } = {},
): Promise<CecchinoApiRawInspectorResponse> {
  const qs = new URLSearchParams()
  if (params.forceRefresh) qs.set('force_refresh', 'true')
  if (params.includeRaw) qs.set('include_raw', 'true')
  if (params.endpoints) qs.set('endpoints', params.endpoints)
  const q = qs.toString()
  return adminGetJson<CecchinoApiRawInspectorResponse>(
    `/api/admin/cecchino/fixtures/${todayFixtureId}/api-raw-inspector${q ? `?${q}` : ''}`,
  )
}

export async function backfillCurrentSeasonXg(
  todayFixtureId: number,
  params: { forceRefresh?: boolean } = {},
): Promise<CecchinoBackfillCurrentSeasonXgResponse> {
  return adminPostJson<CecchinoBackfillCurrentSeasonXgResponse>(
    `/api/admin/cecchino/fixtures/${todayFixtureId}/backfill-current-season-xg`,
    { force_refresh: params.forceRefresh ?? false },
  )
}

function getCecchinoApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error('VITE_API_BASE_URL non configurata.')
  }
  return String(raw).replace(/\/$/, '')
}

async function cecchinoPostJson<T>(path: string, body: unknown = {}): Promise<T> {
  const base = getCecchinoApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  const ct = res.headers.get('content-type') ?? ''
  let parsed: unknown = null
  if (ct.includes('application/json')) {
    try {
      parsed = await res.json()
    } catch {
      parsed = null
    }
  }
  if (!res.ok) {
    const msg =
      parsed && typeof parsed === 'object' && parsed !== null && 'message' in parsed
        ? String((parsed as { message?: string }).message ?? res.statusText)
        : res.statusText
    throw new Error(msg)
  }
  return parsed as T
}

export async function refreshBetfairOdds(
  todayFixtureId: number,
  opts: { force?: boolean; rebuild_kpi?: boolean } = {},
): Promise<CecchinoBetfairRefreshResponse> {
  return cecchinoPostJson<CecchinoBetfairRefreshResponse>(
    `/api/cecchino/today/${todayFixtureId}/refresh-betfair-odds`,
    { force: opts.force ?? true, rebuild_kpi: opts.rebuild_kpi ?? true },
  )
}

export async function getBetfairMarketsJson(
  todayFixtureId: number,
  force = false,
): Promise<CecchinoBetfairMarketsJsonResponse> {
  const q = force ? '?force=true' : '?force=false'
  return requestJson<CecchinoBetfairMarketsJsonResponse>(
    `/api/cecchino/today/${todayFixtureId}/betfair-markets-json${q}`,
  )
}

export async function getCecchinoTodayExcluded(params: {
  date?: string
  timezone?: string
} = {}): Promise<CecchinoTodayExcludedResponse> {
  return requestJson<CecchinoTodayExcludedResponse>(
    `/api/admin/cecchino/today/excluded${qs({ date: params.date, timezone: params.timezone ?? 'Europe/Rome' })}`,
  )
}

export async function debugSearchCecchinoToday(params: {
  date: string
  q: string
}): Promise<CecchinoTodayDebugSearchResponse> {
  return requestJson<CecchinoTodayDebugSearchResponse>(
    `/api/admin/cecchino/today/debug-search${qs({ date: params.date, q: params.q, timezone: 'Europe/Rome' })}`,
  )
}

export async function revalidateCecchinoTodayDay(params: {
  date: string
}): Promise<CecchinoTodayRevalidateDayResponse> {
  return adminPostJson<CecchinoTodayRevalidateDayResponse>('/api/admin/cecchino/today/revalidate-day', {
    date: params.date,
  })
}

export type CecchinoRecomputeResponse = {
  status: string
  fixtures_found: number
  fixtures_recomputed: number
  kpi_recomputed: number
  signals_synced: number
  signals_deactivated: number
  signals_evaluated: number
  warnings: string[]
}

export type CecchinoRecomputeParams = {
  date_from: string
  date_to: string
  scope?: string
  recompute_kpi?: boolean
  recompute_debug?: boolean
  recompute_balance?: boolean
  recompute_icm?: boolean
  recompute_signals?: boolean
  sync_signal_activations?: boolean
  evaluate_signals_after?: boolean
  force_remap_signals?: boolean
  use_existing_bookmaker_odds?: boolean
  refresh_bookmaker_odds?: boolean
}

export async function recomputeCecchino(params: CecchinoRecomputeParams): Promise<CecchinoRecomputeResponse> {
  return adminPostJson<CecchinoRecomputeResponse>('/api/admin/cecchino/recompute', {
    scope: 'cecchino',
    recompute_kpi: true,
    recompute_debug: true,
    recompute_balance: true,
    recompute_icm: true,
    recompute_signals: true,
    sync_signal_activations: true,
    evaluate_signals_after: true,
    force_remap_signals: true,
    use_existing_bookmaker_odds: true,
    refresh_bookmaker_odds: false,
    ...params,
  })
}

const ELIGIBILITY_STATUS_LABELS: Record<string, string> = {
  excluded_missing_bookmaker: 'Bookmaker mancante',
  excluded_missing_1x2_market: 'Mercato 1X2 mancante',
  excluded_insufficient_stats: 'Statistiche insufficienti',
  excluded_missing_picchetto: 'Picchetto mancante',
  excluded_zero_probability: 'Probabilità zero',
  excluded_cecchino_not_calculable: 'Quote finali Cecchino non calcolabili',
  excluded_kpi_not_calculable: 'KPI non calcolabile',
  excluded_leakage_failed: 'Leakage non superato',
  excluded_started: 'Partita già iniziata',
  excluded_cup: 'Coppa / torneo escluso',
  excluded_women: 'Competizione femminile',
  excluded_friendly: 'Amichevole',
  excluded_youth: 'Giovanili',
  excluded_mapping_error: 'Errore mapping',
  error: 'Errore calcolo',
}

export function eligibilityStatusLabel(status: string): string {
  return ELIGIBILITY_STATUS_LABELS[status] ?? status
}

const BLOCKING_WARNING_PATTERNS = [
  /^low_sample:/,
  /^missing_picchetto/,
  /^zero_probability:/,
  /^final_odds_status:/,
  /^missing_final_odds:/,
]

export function isBlockingTodayWarning(w: string): boolean {
  return BLOCKING_WARNING_PATTERNS.some((re) => re.test(w))
}

export function partitionTodayDetailWarnings(warnings: string[] | undefined): {
  notes: string[]
  blocking: string[]
} {
  const notes: string[] = []
  const blocking: string[] = []
  for (const w of warnings ?? []) {
    if (isBlockingTodayWarning(w)) blocking.push(w)
    else notes.push(w)
  }
  return { notes, blocking }
}

export function formatKickoffTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' })
  } catch {
    return iso
  }
}

export function statusBadgeClass(status: MatchDisplayStatus): string {
  switch (status) {
    case 'live':
      return 'bg-red-50 text-red-700 ring-red-200'
    case 'finished':
      return 'bg-slate-100 text-slate-700 ring-slate-200'
    case 'postponed':
    case 'cancelled':
      return 'bg-amber-50 text-amber-800 ring-amber-200'
    default:
      return 'bg-emerald-50 text-emerald-700 ring-emerald-200'
  }
}
