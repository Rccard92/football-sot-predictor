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

export type CecchinoTodayScanJobResultSummary = {
  fixtures_found?: number
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
  api_calls?: Record<string, number>
  api_calls_total?: number
  api_calls_by_endpoint?: Record<string, number>
  odds_strategy?: Record<string, number>
  duration_seconds?: number
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
}

export type CecchinoOddsMeta = {
  odds_source?: string | null
  odds_fetched_at?: string | null
  odds_cached_at?: string | null
  last_betfair_refresh_at?: string | null
  is_cached?: boolean | null
  odds_updated_at?: string | null
}

export type CecchinoKpiV2Panel = {
  version: string
  columns?: string[]
  bookmaker?: {
    name: string
    provider_bookmaker_id: number
    provider_source: string
  }
  bookmaker_status?: string
  odds_meta?: CecchinoOddsMeta
  rows: CecchinoKpiV2Row[]
  warnings?: string[]
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
  status: 'official' | 'research' | 'calibration_pending' | 'unavailable' | string
  index: number | null
  class_label: string | null
  reading: string
  direction: string | null
  source_version: string | null
  components: CecchinoBalanceV5Component[]
  warnings: string[]
}

export type CecchinoBalanceV5MarketPair = {
  key: string
  label: string
  quota_cecchino?: number | null
  quota_book?: number | null
  prob_cecchino_pct?: number | null
  prob_book_pct?: number | null
  deviation_pp?: number | null
}

export type CecchinoBalanceV5MarketDeviation = {
  title: string
  subtitle: string
  status: string
  index?: number | null
  class_label?: string | null
  pairs: CecchinoBalanceV5MarketPair[]
  reading: string
  warnings?: string[]
  has_book_data?: boolean
}

export type CecchinoBalanceV5Preview = {
  status?: 'ok' | 'unavailable' | string
  version: string
  pillars: CecchinoBalanceV5Pillar[]
  market_deviation: CecchinoBalanceV5MarketDeviation
  research_note: string
  production_changes: boolean
  research_candidates?: Record<string, unknown>
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
  kpi_panel?: CecchinoKpiV2Panel
  kpi_panel_v2?: CecchinoKpiV2Panel
  picchetti_debug_summary?: CecchinoPicchettiDebugSummary
  icm_analysis?: CecchinoIcmAnalysis
  balance_analysis?: CecchinoBalanceAnalysis
  balance_v5_preview?: CecchinoBalanceV5Preview
  balance_v5?: CecchinoBalanceV5Preview
  fixture_identity_consistency?: CecchinoFixtureIdentityConsistency
  goal_intensity_analysis?: CecchinoGoalIntensityAnalysis
  expected_goal_engine_diagnostics?: CecchinoExpectedGoalEngineDiagnostics
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
