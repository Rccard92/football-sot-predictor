/** Client HTTP verso il backend. Base URL da `VITE_API_BASE_URL` (senza trailing slash). */

import type { FixtureLineupsResponse } from '../types/fixtureLineups'
import type { SportApiFixtureDebugResponse, SportApiLineupsStoredResponse } from '../types/sportapi'
import type { FixturePlayerProfilesResponse } from '../types/playerDbProfiles'

export const DEFAULT_SEASON = Number(import.meta.env.VITE_DEFAULT_SEASON) || 2025

export type LeagueDashboardBlock = {
  id: number
  api_league_id: number
  name: string
  country: string | null
  logo_url: string | null
}

export type SeasonDashboardBlock = {
  id: number
  league_id: number
  year: number
  label: string | null
  is_current: boolean
}

export type DataCoverageBlock = {
  teams_imported: boolean
  fixtures_imported: boolean
}

export type IngestionRunSummary = {
  id: number
  source: string
  status: string
  records_processed: number
  error_message: string | null
  meta: Record<string, unknown> | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

/** Allineato a [`backend/app/schemas/dashboard.py`](SerieADashboardResponse). */
export type SerieADashboardResponse = {
  league: LeagueDashboardBlock | null
  season: SeasonDashboardBlock | null
  teams_total: number
  fixtures_total: number
  fixtures_completed: number
  fixtures_scheduled: number
  fixtures_live_or_unknown: number
  fixtures_with_team_stats: number
  team_stats_rows_total: number
  team_stats_coverage_pct: number
  sot_feature_rows_total: number
  sot_feature_expected_rows: number
  sot_feature_coverage_pct: number
  sot_predictions_total: number
  sot_predictions_expected: number
  sot_predictions_coverage_pct: number
  avg_expected_sot: number
  avg_prediction_confidence: number
  sot_backtests_total: number
  sot_backtests_expected: number
  sot_backtest_coverage_pct: number
  sot_backtest_mae: number
  sot_backtest_rmse: number
  sot_backtest_avg_expected_sot: number
  sot_backtest_avg_actual_sot: number
  upcoming_fixtures_total: number
  upcoming_sot_feature_rows_total: number
  upcoming_sot_predictions_total: number
  standings_snapshot_available?: boolean
  standings_snapshot_at?: string | null
  next_round?: string | null
  v02_predictions_upcoming?: number
  v02_avg_total_adjustment?: number
  v02_avg_player_adjustment?: number
  v02_avg_h2h_adjustment?: number
  v02_avg_motivation_adjustment?: number
  v02_matches_with_context_warning?: number
  last_ingestion_run: IngestionRunSummary | null
  data_coverage: DataCoverageBlock
  fixtures_with_player_stats?: number
  player_stats_rows_total?: number
  player_stats_coverage_pct?: number
  fixtures_with_lineups?: number
  lineups_rows_total?: number
  lineups_coverage_pct?: number
  players_profiled_total?: number
  player_profiles_total?: number
  player_profiles_sot_data_suspicious?: boolean
  availability_events_total?: number
}

export type SerieADataHealthResponse = {
  fixtures_completed: number
  fixtures_with_team_stats: number
  fixtures_missing_team_stats: number
  missing_fixture_ids?: number[]
  team_stats_rows_total: number
  team_stats_coverage_pct: number
}

export type IngestionRunsResponse = {
  runs: IngestionRunSummary[]
  total: number
}

export type SotPredictionsSeasonSummaryResponse = {
  season: number
  model_version: string
  feature_rows_total: number
  predictions_total: number
  coverage_pct: number
  avg_expected_sot: number
  min_expected_sot: number
  max_expected_sot: number
  avg_confidence_score: number
}

export type BacktestNumericSummaryResponse = {
  season: number
  model_version: string
  predictions_total: number
  backtests_total: number
  coverage_pct: number
  mae: number
  rmse: number
  avg_expected_sot: number
  avg_actual_sot: number
  avg_absolute_error: number
  max_absolute_error: number
}

export type BacktestByTeamRow = {
  team_id: number
  team_name: string
  predictions_count: number
  avg_expected_sot: number
  avg_actual_sot: number
  mae: number
  rmse: number
  max_absolute_error: number
}

export type BacktestByTeamListResponse = {
  season: number
  model_version: string
  teams: BacktestByTeamRow[]
}

export type BacktestBySideRow = {
  side: string
  predictions_count: number
  avg_expected_sot: number
  avg_actual_sot: number
  mae: number
  rmse: number
}

export type BacktestBySideListResponse = {
  season: number
  model_version: string
  sides: BacktestBySideRow[]
}

export type ModelLegendStatus =
  | 'applicata'
  | 'solo_debug'
  | 'applicata_alla_lettura'
  | 'non_applicata'

export type ModelLegendVariable = {
  technical_key: string
  name: string
  description: string
  weight: number | null
  weight_label: string | null
  status: ModelLegendStatus
  impact: string
  interpretation: string
}

export type ModelLegendSection = {
  id: string
  title: string
  status: ModelLegendStatus
  description: string
  variables: ModelLegendVariable[]
}

export type ModelLegendResponse = {
  model_version: string
  title: string
  description: string
  expected_sot_formula: string
  sections: ModelLegendSection[]
}

export type FrameworkImplementationStatus =
  | 'implementata'
  | 'parzialmente implementata'
  | 'solo debug'
  | 'da implementare'
  | 'non disponibile'

export type FrameworkMarketId =
  | 'tiri_in_porta'
  | 'tiri_totali'
  | 'corner'
  | 'cartellini'
  | 'falli'
  | 'goal_over_under'

export type MatchAnalysisFrameworkVariable = {
  area: string
  key: string
  name: string
  description: string
  impacted_markets: FrameworkMarketId[]
  theoretical_weight: number
  weight_label: string
  data_source: string
  implementation_status: FrameworkImplementationStatus
  applied_now: boolean
  notes?: string | null
  applied_layer?: string | null
  direct_formula_impact?: boolean | null
  decision_context_impact?: boolean | null
  applied_to_model_versions?: string[] | null
  application_role?: string | null
  parent_component?: string | null
  expected_in_debug?: boolean | null
}

export type MatchAnalysisFrameworkArea = {
  id: string
  title: string
  description: string
  variables: MatchAnalysisFrameworkVariable[]
}

export type MatchAnalysisMarketFramework = {
  id: FrameworkMarketId
  title: string
  primary_variables: string[]
  secondary_variables: string[]
  warning_variables: string[]
  less_relevant_variables: string[]
}

export type MatchAnalysisFrameworkResponse = {
  title: string
  description: string
  version: string
  areas: MatchAnalysisFrameworkArea[]
  market_frameworks: MatchAnalysisMarketFramework[]
  future_editable_weights: {
    enabled_now: boolean
    planned: boolean
    description: string
  }
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

function extractErrorMessage(body: unknown, statusText: string): string {
  if (body && typeof body === 'object') {
    const o = body as Record<string, unknown>
    if (typeof o.message === 'string') return o.message
    if (typeof o.detail === 'string') return o.detail
    if (Array.isArray(o.detail)) {
      const first = o.detail[0] as Record<string, unknown> | undefined
      if (first && typeof first.msg === 'string') return first.msg
    }
  }
  return statusText || 'Richiesta non riuscita'
}

/** Errore HTTP da chiamate admin (include status e body JSON se presente). */
export class AdminHttpError extends Error {
  readonly status: number
  readonly body: unknown
  constructor(status: number, message: string, body: unknown) {
    super(message)
    this.name = 'AdminHttpError'
    this.status = status
    this.body = body
  }
}

async function requestJson<T>(path: string): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`)

  const ct = res.headers.get('content-type') ?? ''
  let body: unknown = null
  if (ct.includes('application/json')) {
    try {
      body = await res.json()
    } catch {
      body = null
    }
  }

  if (!res.ok) {
    throw new Error(extractErrorMessage(body, res.statusText))
  }

  if (body && typeof body === 'object' && 'status' in body) {
    const st = (body as Record<string, unknown>).status
    if (st === 'error') {
      throw new Error(extractErrorMessage(body, 'Errore API'))
    }
  }

  return body as T
}

/** POST: non interpreta `status: error` nel body come eccezione se HTTP 2xx (allineato ai route admin). */
async function requestPostJson<T>(path: string, body: unknown = {}): Promise<T> {
  const base = getApiBase()
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
    throw new Error(extractErrorMessage(parsed, res.statusText))
  }

  return parsed as T
}

/** Opzioni per richieste admin lunghe (timeout client + AbortSignal). */
export type AdminRequestOpts = {
  signal?: AbortSignal
  /** Se impostato, abort dopo N ms (messaggio: Timeout operazione). */
  timeoutMs?: number
}

function createLinkedTimeoutSignal(timeoutMs: number, outer?: AbortSignal): { signal: AbortSignal; cancel: () => void } {
  const c = new AbortController()
  const tid = window.setTimeout(() => {
    c.abort(new Error(`Timeout operazione dopo ${Math.round(timeoutMs / 1000)} s`))
  }, timeoutMs)
  const cancel = () => window.clearTimeout(tid)
  if (outer) {
    const onOuter = () => {
      cancel()
      try {
        c.abort(outer.reason)
      } catch {
        c.abort()
      }
    }
    if (outer.aborted) {
      onOuter()
    } else {
      outer.addEventListener('abort', onOuter, { once: true })
    }
  }
  return { signal: c.signal, cancel }
}

async function requestPostJsonWithOpts<T>(path: string, body: unknown = {}, opts?: AdminRequestOpts): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  let cancelTimeout: (() => void) | undefined
  let signal: AbortSignal | undefined = opts?.signal
  if (opts?.timeoutMs != null && opts.timeoutMs > 0) {
    const x = createLinkedTimeoutSignal(opts.timeoutMs, opts.signal)
    signal = x.signal
    cancelTimeout = x.cancel
  }
  try {
    const res = await fetch(`${base}${p}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
      signal,
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
      throw new AdminHttpError(res.status, extractErrorMessage(parsed, res.statusText), parsed)
    }

    return parsed as T
  } finally {
    cancelTimeout?.()
  }
}

async function requestJsonWithOpts<T>(path: string, opts?: AdminRequestOpts): Promise<T> {
  const base = getApiBase()
  const urlPath = path.startsWith('/') ? path : `/${path}`
  let cancelTimeout: (() => void) | undefined
  let signal: AbortSignal | undefined = opts?.signal
  if (opts?.timeoutMs != null && opts.timeoutMs > 0) {
    const x = createLinkedTimeoutSignal(opts.timeoutMs, opts.signal)
    signal = x.signal
    cancelTimeout = x.cancel
  }
  try {
    const res = await fetch(`${base}${urlPath}`, { method: 'GET', signal })

    const ct = res.headers.get('content-type') ?? ''
    let body: unknown = null
    if (ct.includes('application/json')) {
      try {
        body = await res.json()
      } catch {
        body = null
      }
    }

    if (!res.ok) {
      throw new AdminHttpError(res.status, extractErrorMessage(body, res.statusText), body)
    }

    if (body && typeof body === 'object' && 'status' in body) {
      const st = (body as Record<string, unknown>).status
      if (st === 'error') {
        throw new AdminHttpError(
          res.status,
          extractErrorMessage(body, 'Errore API'),
          body,
        )
      }
    }

    return body as T
  } finally {
    cancelTimeout?.()
  }
}

/** Pipeline completa refresh + v0.4 (può durare molti minuti). */
export async function postRefreshUpcomingV04Pipeline(
  season: number,
  opts?: AdminRequestOpts,
): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 900_000
  return requestPostJsonWithOpts<unknown>(
    `/api/admin/pipeline/serie-a/${season}/refresh-upcoming-v04`,
    {},
    { ...opts, timeoutMs },
  )
}

/** Solo generazione previsioni upcoming modello v0.4 offensive core SOT. */
export async function postGenerateV04OffensiveCoreSotUpcoming(
  season: number,
  opts?: AdminRequestOpts,
): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 300_000
  return requestPostJsonWithOpts<unknown>(
    `/api/predictions/sot/serie-a/${season}/generate-v04-offensive-core-sot`,
    {},
    { ...opts, timeoutMs },
  )
}

/** Generazione previsioni upcoming baseline_v1_0_sot (correzione xG su v0.4). */
export async function postGenerateV10SotUpcoming(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 300_000
  return requestPostJsonWithOpts<unknown>(
    `/api/predictions/sot/serie-a/${season}/generate-v10-sot`,
    {},
    { ...opts, timeoutMs },
  )
}

/** Generazione previsioni upcoming baseline_v1_1_sot (stage 1: produzione offensiva, solo dati reali). */
export async function postGenerateV11SotUpcoming(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 300_000
  return requestPostJsonWithOpts<unknown>(
    `/api/predictions/sot/serie-a/${season}/generate-v11-sot`,
    {},
    { ...opts, timeoutMs },
  )
}

/** GET admin/diagnostica con timeout opzionale. */
export async function getModelStatusWithOpts(season: number, opts?: AdminRequestOpts): Promise<ModelStatusResponse> {
  return requestJsonWithOpts<ModelStatusResponse>(
    `/api/predictions/sot/serie-a/${season}/model-status`,
    { ...opts, timeoutMs: opts?.timeoutMs ?? 60_000 },
  )
}

export async function getUpcomingActiveWithOpts(
  season: number,
  query: { limit?: number; onlyNextRound?: boolean; modelVersion?: string | null },
  opts?: AdminRequestOpts,
): Promise<UpcomingActiveResponse> {
  const p = new URLSearchParams()
  if (query.limit != null) p.set('limit', String(query.limit))
  if (query.onlyNextRound != null) p.set('only_next_round', String(query.onlyNextRound))
  if (query.modelVersion) p.set('model_version', query.modelVersion)
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming-active${q ? `?${q}` : ''}`
  return requestJsonWithOpts<UpcomingActiveResponse>(path, { ...opts, timeoutMs: opts?.timeoutMs ?? 60_000 })
}

/** POST ingest/admin generici con timeout client predefinito (3 min). */
export async function adminPostJson<T>(path: string, body: unknown = {}, opts?: AdminRequestOpts): Promise<T> {
  return requestPostJsonWithOpts<T>(path, body, { timeoutMs: 180_000, ...opts })
}

/** GET admin/diagnostica con timeout predefinito (90 s). */
export async function adminGetJson<T>(path: string, opts?: AdminRequestOpts): Promise<T> {
  return requestJsonWithOpts<T>(path, { ...opts, timeoutMs: opts?.timeoutMs ?? 90_000 })
}

export async function getDashboard(season: number): Promise<SerieADashboardResponse> {
  return requestJson<SerieADashboardResponse>(`/api/dashboard/serie-a/${season}`)
}

export async function getDataHealth(season: number): Promise<SerieADataHealthResponse> {
  return requestJson<SerieADataHealthResponse>(`/api/admin/data-health/serie-a/${season}`)
}

/** Risposta GET `/api/admin/debug/serie-a/{season}/team-shot-stats-summary`. */
export type TeamShotStatsCoverageEntry = {
  rows_with_value: number
  coverage_pct: number
}

export type TeamShotStatsSummaryResponse = {
  status: string
  season: number
  rows_total: number
  coverage: Record<string, TeamShotStatsCoverageEntry>
  column_null_but_raw_parseable: { blocked_shots: number; shots_off_goal: number }
  sample: Array<{
    fixture_id: number
    team_id: number
    team_name: string
    shots_on_target: number | null
    total_shots: number | null
    shots_inside_box: number | null
    shots_outside_box: number | null
    blocked_shots: number | null
    shots_off_goal: number | null
  }>
}

export async function getTeamShotStatsSummary(
  season: number,
  opts?: AdminRequestOpts,
): Promise<TeamShotStatsSummaryResponse> {
  return adminGetJson<TeamShotStatsSummaryResponse>(
    `/api/admin/debug/serie-a/${season}/team-shot-stats-summary`,
    opts,
  )
}

export async function getIngestionRuns(): Promise<IngestionRunsResponse> {
  return requestJson<IngestionRunsResponse>('/api/admin/ingest/runs')
}

export async function getPredictionSummary(
  season: number,
): Promise<SotPredictionsSeasonSummaryResponse> {
  return requestJson<SotPredictionsSeasonSummaryResponse>(
    `/api/predictions/sot/serie-a/${season}/summary`,
  )
}

export async function getBacktestSummary(season: number): Promise<BacktestNumericSummaryResponse> {
  return requestJson<BacktestNumericSummaryResponse>(
    `/api/backtest/sot/serie-a/${season}/summary`,
  )
}

export async function getBacktestByTeam(season: number): Promise<BacktestByTeamListResponse> {
  return requestJson<BacktestByTeamListResponse>(
    `/api/backtest/sot/serie-a/${season}/by-team`,
  )
}

export async function getBacktestBySide(season: number): Promise<BacktestBySideListResponse> {
  return requestJson<BacktestBySideListResponse>(
    `/api/backtest/sot/serie-a/${season}/by-side`,
  )
}

export async function getModelLegend(): Promise<ModelLegendResponse> {
  return requestJson<ModelLegendResponse>('/api/model/legend')
}

/** Campo diretto da scan API-Football. */
export type ApiFootballDirectField = {
  stable_id: string
  json_path: string
  endpoint: string
  appeared_in_endpoints: string[]
  area_id: string
  technical_name: string
  name_it: string
  name_it_auto: boolean
  description_it: string
  tooltip_it: string | null
  sample_value: unknown
  sample_type: string
  examples_count: number
  appeared_in_raw_json: boolean
  api_label: string
  db_status: string
  db_location_hint: string | null
  model_v04_status: string
  note_it: string | null
}

export type ApiFootballDirectArea = {
  id: string
  title: string
  endpoints: string[]
  direct_fields_found: number
  fields_saved_in_db: number
  fields_raw_json_only: number
  fields_used_by_v04: number
  parameters: ApiFootballDirectField[]
}

export type ApiFootballDirectCatalogSummary = {
  endpoints_scanned: number
  endpoints_errors: number
  direct_fields_found: number
  fields_used_by_v04: number
  fields_saved_in_db: number
  fields_raw_json_only: number
}

export type ApiFootballDirectCatalogResponse = {
  version: string
  season?: number | null
  provider: string
  last_scan_at?: string | null
  message?: string
  summary: ApiFootballDirectCatalogSummary
  areas: ApiFootballDirectArea[]
}

export type ApiFootballScanDiagnostic = {
  endpoint: string
  params: Record<string, unknown>
  status: string
  fields_found: number
  error: string | null
  trace?: string
}

export type ApiFootballDirectScanResponse = ApiFootballDirectCatalogResponse & {
  diagnostics?: ApiFootballScanDiagnostic[]
}

export async function getApiFootballCatalogDirect(): Promise<ApiFootballDirectCatalogResponse> {
  return requestJson<ApiFootballDirectCatalogResponse>('/api/data-catalog/api-football/direct')
}

/** Campo catalogo model-relevant (file statico classificato). */
export type ModelRelevantField = {
  key: string
  area: string
  endpoint: string
  json_path: string
  name_it: string
  technical_name: string
  sample_type: string
  sample_value?: unknown
  db_status?: string
  db_location_hint?: string | null
  model_v04_status: string
  classification: string
  priority?: string
  recommended_markets?: string
  reason?: string
  selectable: boolean
  original_json_path?: string
  occurrences_collapsed?: number
  /** Opzionale: se assente in JSON, in UI si usa `key` come identificativo stabile. */
  stable_id?: string
  /** Solo UI: dopo deduplicazione catalogo, tutte le key unite. */
  merged_catalog_keys?: string[]
  /** Solo UI: fonti alternative assorbite nel record primario. */
  alternative_sources?: { endpoint: string; stable_id: string; json_path: string }[]
  /** Solo UI: testo per ricerca su endpoint/key duplicati. */
  dedupe_search_blob?: string
}

export type ModelRelevantArea = {
  id: string
  title: string
  parameters: ModelRelevantField[]
}

export type ModelRelevantCatalogSummary = {
  model_field_count: number
  technical_derivative_count: number
  area_count: number
  fields_used_by_v04_in_model_catalog?: number
  raw_fields_original?: number | null
  hide_from_model_catalog?: number | null
}

export type ModelRelevantCatalogResponse = {
  version: string
  message?: string | null
  source: Record<string, unknown>
  summary: ModelRelevantCatalogSummary
  areas: ModelRelevantArea[]
  technical_derivative_sources: {
    title: string
    fields: ModelRelevantField[]
  }
}

export async function getApiFootballModelRelevantCatalog(): Promise<ModelRelevantCatalogResponse> {
  return requestJson<ModelRelevantCatalogResponse>('/api/data-catalog/model-relevant')
}

export async function postAdminDebugApiFootballCatalogScan(
  season: number,
): Promise<ApiFootballDirectScanResponse> {
  return requestPostJson<ApiFootballDirectScanResponse>(
    `/api/admin/debug/api-football-catalog/serie-a/${season}/scan`,
    {},
  )
}

export async function getMatchAnalysisFramework(): Promise<MatchAnalysisFrameworkResponse> {
  return requestJson<MatchAnalysisFrameworkResponse>('/api/model/match-analysis-framework')
}

export async function runBuildSotFeatures(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/features/sot/serie-a/${season}/build`, {}, { timeoutMs: 300_000, ...opts })
}

export async function runGenerateSotPredictions(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/predictions/sot/serie-a/${season}/generate`, {}, { timeoutMs: 300_000, ...opts })
}

export async function runSotBacktest(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/backtest/sot/serie-a/${season}/run`, {}, { timeoutMs: 300_000, ...opts })
}

/** Allineato a `UpcomingSotCalculationBreakdown` (backend). */
export type UpcomingCalculationBreakdown = {
  season_avg_sot_for: number
  season_avg_sot_for_weight: number
  season_avg_sot_for_contribution: number
  season_avg_sot_for_fallback_used?: boolean
  season_avg_sot_for_fallback_note?: string | null
  opponent_season_avg_sot_conceded: number
  opponent_season_avg_sot_conceded_weight: number
  opponent_season_avg_sot_conceded_contribution: number
  opponent_season_avg_sot_conceded_fallback_used?: boolean
  opponent_season_avg_sot_conceded_fallback_note?: string | null
  home_away_avg_sot_for: number
  home_away_avg_sot_for_weight: number
  home_away_avg_sot_for_contribution: number
  home_away_avg_sot_for_fallback_used?: boolean
  home_away_avg_sot_for_fallback_note?: string | null
  opponent_home_away_avg_sot_conceded: number
  opponent_home_away_avg_sot_conceded_weight: number
  opponent_home_away_avg_sot_conceded_contribution: number
  opponent_home_away_avg_sot_conceded_fallback_used?: boolean
  opponent_home_away_avg_sot_conceded_fallback_note?: string | null
  last5_avg_sot_for: number
  last5_avg_sot_for_weight: number
  last5_avg_sot_for_contribution: number
  last5_avg_sot_for_fallback_used?: boolean
  last5_avg_sot_for_fallback_note?: string | null
  opponent_last5_avg_sot_conceded: number
  opponent_last5_avg_sot_conceded_weight: number
  opponent_last5_avg_sot_conceded_contribution: number
  opponent_last5_avg_sot_conceded_fallback_used?: boolean
  opponent_last5_avg_sot_conceded_fallback_note?: string | null
  expected_sot_total: number
}

export type UpcomingSidePrediction = {
  expected_sot: number
  confidence_score: number
  confidence_label: string
  data_quality_score?: number
  data_quality_label?: string
  prediction_confidence_score?: number
  prediction_confidence_label?: string
  label: string
  simple_explanation: string
  calculation_breakdown: UpcomingCalculationBreakdown | null
}

export type UpcomingMatchTeam = {
  id: number
  name: string
  logo_url: string | null
}

export type UpcomingMatchRow = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: UpcomingMatchTeam
  away_team: UpcomingMatchTeam
  home_prediction: UpcomingSidePrediction | null
  away_prediction: UpcomingSidePrediction | null
  total_expected_sot: number | null
  context_status?: string
  match_context?: Record<string, unknown> | null
  home_team_context?: Record<string, unknown> | null
  away_team_context?: Record<string, unknown> | null
  h2h_summary?: Record<string, unknown> | null
  player_impact_status?: Record<string, unknown> | null
}

export type ModelLimitations = {
  lineups_considered: boolean
  injuries_considered: boolean
  odds_automatically_imported: boolean
  note: string
}

export type UpcomingMatchesResponse = {
  season: number
  round: string | null
  matches_count: number
  matches: UpcomingMatchRow[]
  model_limitations: ModelLimitations
  v02_available?: boolean
}

export type ModelStatusVersionRow = {
  model_version: string
  predictions_total: number
  upcoming_predictions: number
  avg_expected_sot: number | null
  min_expected_sot: number | null
  max_expected_sot: number | null
  generated_at: string | null
  is_available_for_upcoming: boolean
  xg_applied_count?: number
  xg_fallback_count?: number
  valid_predictions?: number
  incomplete_predictions?: number
  missing_required_data_count?: number
  missing_fields_summary?: Record<string, number>
}

export type ModelStatusResponse = {
  status?: string
  season: number
  active_model_version: string | null
  recommended_model_version?: string | null
  upcoming_fixtures_total?: number
  available_model_versions: ModelStatusVersionRow[]
  warnings: string[]
  /** Presente quando ci sono conteggi su feature mancanti per predizioni v1.1 incomplete. */
  v11_diagnostic_hints?: {
    missing_fields_summary: Record<string, number>
    top_missing_feature_keys: string[]
  }
  message?: string
  failed_step?: string
  details?: string
}

export type UpcomingActiveSidePrediction = {
  expected_sot: number
  model_version: string
  baseline_v01_expected_sot: number | null
  difference_from_v01: number | null
  breakdown: Record<string, unknown> | null
}

export type UpcomingActiveMatchRow = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: UpcomingMatchTeam
  away_team: UpcomingMatchTeam
  model_version_used: string
  home_prediction: UpcomingActiveSidePrediction | null
  away_prediction: UpcomingActiveSidePrediction | null
  total_expected_sot: number | null
}

export type UpcomingActiveResponse = {
  season: number
  model_version_used: string
  recommended_model_version: string
  round: string | null
  matches_count: number
  matches: UpcomingActiveMatchRow[]
  model_limitations: ModelLimitations
  warnings: string[]
}

export type UpcomingV02SidePrediction = {
  baseline_expected_sot: number
  adjusted_expected_sot: number
  total_adjustment: number
  player_adjustment: number
  h2h_adjustment: number
  motivation_adjustment: number
  availability_adjustment: number
  prediction_confidence_score_v0_2: number
  prediction_confidence_label_v0_2: string
  adjustment_breakdown?: Record<string, unknown> | null
  adjustments?: Record<string, unknown> | null
}

export type UpcomingV02MatchRow = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: UpcomingMatchTeam
  away_team: UpcomingMatchTeam
  home_prediction_v02: UpcomingV02SidePrediction | null
  away_prediction_v02: UpcomingV02SidePrediction | null
  total_expected_sot_baseline: number | null
  total_expected_sot_v02: number | null
}

export type UpcomingV02Response = {
  status: 'success' | 'error'
  season: number
  model_version: string
  matches_count: number
  matches: UpcomingV02MatchRow[]
}

export type PlayerAdjustedTopPlayer = {
  player_id: number
  name: string
  impact_score: number | null
  shots_on_target_per90: number | null
  total_minutes: number
  appearances: number
  sample_warning?: boolean
}

export type PlayerAdjustedBreakdown = {
  applied: boolean
  team_top5_avg_impact?: number
  league_avg_top5_impact?: number
  player_strength_ratio?: number
  adjustment: number
  cap: number
  sample_warning?: boolean
  top_players_considered: PlayerAdjustedTopPlayer[]
  explanation: string
}

export type UpcomingPlayerAdjustedSide = {
  baseline_expected_sot: number
  adjusted_expected_sot: number
  player_adjustment: number
  total_adjustment: number
  adjustment_breakdown: {
    player_adjustment?: PlayerAdjustedBreakdown | null
    h2h_adjustment?: { applied: boolean; adjustment: number } | null
    motivation_adjustment?: { applied: boolean; adjustment: number } | null
    availability_adjustment?: { applied: boolean; adjustment: number } | null
  }
}

export type UpcomingPlayerAdjustedMatchRow = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home_team: UpcomingMatchTeam
  away_team: UpcomingMatchTeam
  home: UpcomingPlayerAdjustedSide | null
  away: UpcomingPlayerAdjustedSide | null
  total_expected_sot_baseline: number | null
  total_expected_sot_adjusted: number | null
}

export type UpcomingPlayerAdjustedResponse = {
  status: 'success' | 'error'
  season: number
  model_version: string
  matches_count: number
  matches: UpcomingPlayerAdjustedMatchRow[]
}

export type UpcomingV03CoreSotSide = {
  team_id: number
  expected_sot_v01: number | null
  expected_sot_v03: number | null
  difference_from_v01: number | null
  core_sot_component: number | null
  shot_volume_component: number | null
  shot_accuracy_component: number | null
  recent_form_component: number | null
  goals_context_component: number | null
  breakdown: Record<string, unknown> | null
}

export type UpcomingV03CoreSotMatchRow = {
  fixture_id: number
  api_fixture_id: number
  round: string | null
  kickoff_at: string
  status_short: string
  home: UpcomingV03CoreSotSide | null
  away: UpcomingV03CoreSotSide | null
}

export type UpcomingV03CoreSotResponse = {
  status: 'success' | 'error'
  model_version: string
  matches: UpcomingV03CoreSotMatchRow[]
}

export type EvaluateSotLineResponse = {
  expected_sot: number
  line_value: number
  gap: number
  suggestion: 'over' | 'under' | 'no_bet'
  strength: 'forte' | 'interessante' | 'leggero' | 'neutro'
  label: string
  explanation: string
}

export async function getUpcomingPredictions(
  season: number,
  opts?: { limit?: number; onlyNextRound?: boolean; round?: string },
): Promise<UpcomingMatchesResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  if (opts?.round) p.set('round', opts.round)
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming${q ? `?${q}` : ''}`
  return requestJson<UpcomingMatchesResponse>(path)
}

export async function getModelStatus(season: number): Promise<ModelStatusResponse> {
  const path = `/api/predictions/sot/serie-a/${season}/model-status`
  return requestJson<ModelStatusResponse>(path)
}

export async function getUpcomingActive(
  season: number,
  opts?: { limit?: number; onlyNextRound?: boolean; modelVersion?: string | null },
): Promise<UpcomingActiveResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming-active${q ? `?${q}` : ''}`
  return requestJson<UpcomingActiveResponse>(path)
}

export async function buildUpcomingSotFeatures(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/features/sot/serie-a/${season}/build-upcoming`, {}, opts)
}

export async function generateUpcomingSotPredictions(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/predictions/sot/serie-a/${season}/generate-upcoming`, {}, opts)
}

export async function generateUpcomingSotPredictionsV02(season: number): Promise<unknown> {
  return requestPostJson<unknown>(`/api/predictions/sot/serie-a/${season}/generate-v02-upcoming`, {})
}

export async function getUpcomingPredictionsV02(
  season: number,
  opts?: { limit?: number; onlyNextRound?: boolean },
): Promise<UpcomingV02Response> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming-v02${q ? `?${q}` : ''}`
  return requestJson<UpcomingV02Response>(path)
}

export async function getUpcomingV02PlayerAdjusted(
  season: number,
  opts?: { limit?: number; onlyNextRound?: boolean },
): Promise<UpcomingPlayerAdjustedResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming-v02-player-adjusted${q ? `?${q}` : ''}`
  return requestJson<UpcomingPlayerAdjustedResponse>(path)
}

export async function getUpcomingV03CoreSot(
  season: number,
  opts?: { limit?: number; onlyNextRound?: boolean },
): Promise<UpcomingV03CoreSotResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming-v03-core-sot${q ? `?${q}` : ''}`
  return requestJson<UpcomingV03CoreSotResponse>(path)
}

export async function adminRefreshPostMatchday(
  season: number,
  forceUpdate = false,
  opts?: AdminRequestOpts,
): Promise<unknown> {
  return requestPostJsonWithOpts<unknown>(
    `/api/admin/refresh/serie-a/${season}/post-matchday?force_update=${String(forceUpdate)}`,
    {},
    { timeoutMs: 900_000, ...opts },
  )
}

export async function adminIngestStandings(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/standings`, {}, opts)
}

export async function adminRegenerateUpcomingPredictions(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  await adminPostJson<unknown>(`/api/features/sot/serie-a/${season}/build-upcoming`, {}, opts)
  return adminPostJson<unknown>(`/api/predictions/sot/serie-a/${season}/generate-upcoming`, {}, opts)
}

export async function evaluateSotLine(
  expectedSot: number,
  lineValue: number,
): Promise<EvaluateSotLineResponse> {
  return requestPostJson<EvaluateSotLineResponse>('/api/predictions/sot/evaluate-line', {
    expected_sot: expectedSot,
    line_value: lineValue,
  })
}

export type EvaluateMatchSotLineBody = {
  home_expected_sot: number
  away_expected_sot: number
  home_adjusted_expected_sot?: number | null
  away_adjusted_expected_sot?: number | null
  use_adjusted?: boolean
  market_type?: string
  line_value: number
  odds?: number | null
  bookmaker: string
}

export type EvaluateMatchSotLineResponse = {
  market_type: string
  bookmaker: string
  line_value: number
  odds: number | null
  home_expected_sot: number
  away_expected_sot: number
  total_expected_sot: number
  gap: number
  suggestion: 'over' | 'under' | 'no_bet'
  strength: 'forte' | 'interessante' | 'leggero' | 'neutro'
  label: string
  implied_probability: number | null
  explanation: string
  model_used?: string | null
  baseline_total_expected_sot?: number | null
  adjusted_total_expected_sot?: number | null
  baseline_gap?: number | null
  adjusted_gap?: number | null
  warning?: string | null
}

export async function evaluateMatchLine(
  body: EvaluateMatchSotLineBody,
): Promise<EvaluateMatchSotLineResponse> {
  return requestPostJson<EvaluateMatchSotLineResponse>('/api/predictions/sot/evaluate-match-line', {
    home_expected_sot: body.home_expected_sot,
    away_expected_sot: body.away_expected_sot,
    ...(body.home_adjusted_expected_sot != null
      ? { home_adjusted_expected_sot: body.home_adjusted_expected_sot }
      : {}),
    ...(body.away_adjusted_expected_sot != null
      ? { away_adjusted_expected_sot: body.away_adjusted_expected_sot }
      : {}),
    use_adjusted: body.use_adjusted ?? false,
    market_type: body.market_type ?? 'match_total_sot',
    line_value: body.line_value,
    bookmaker: body.bookmaker,
    ...(body.odds != null && body.odds > 0 ? { odds: body.odds } : {}),
  })
}

export async function adminBootstrapSerieA(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/bootstrap`, {}, opts)
}

export async function adminIngestTeamStats(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/team-stats`, {}, opts)
}

export async function adminIngestPlayerMatchStats(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/player-match-stats`, {}, opts)
}

export async function getPlayerMatchDbSummary(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminGetJson<unknown>(`/api/admin/debug/serie-a/${season}/player-db-summary`, opts)
}

export async function buildPlayerSeasonProfiles(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(
    `/api/admin/features/player-season-profiles/serie-a/${season}/build`,
    {},
    opts,
  )
}

export type PlayerProfilesLimit = 10 | 15 | 25 | 'all'

export async function getFixturePlayerProfiles(
  fixtureId: number,
  opts?: { season?: number; limit?: PlayerProfilesLimit },
): Promise<FixturePlayerProfilesResponse> {
  const base = getApiBase()
  const q = new URLSearchParams()
  if (opts?.season != null) q.set('season', String(opts.season))
  if (opts?.limit != null) q.set('limit', opts.limit === 'all' ? 'all' : String(opts.limit))
  const qs = q.toString()
  const path = `/api/debug/sot/fixture/${fixtureId}/player-profiles${qs ? `?${qs}` : ''}`
  const res = await fetch(`${base}${path}`)
  return (await res.json()) as FixturePlayerProfilesResponse
}

export async function adminIngestPlayerStats(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/player-stats`, {}, opts)
}

export type LineupsIngestOptions = {
  fixtureId?: number
  force?: boolean
}

export async function adminIngestLineups(
  season: number,
  ingestOpts?: LineupsIngestOptions,
  opts?: AdminRequestOpts,
): Promise<unknown> {
  const params = new URLSearchParams()
  if (ingestOpts?.fixtureId != null) params.set('fixture_id', String(ingestOpts.fixtureId))
  if (ingestOpts?.force) params.set('force', 'true')
  const qs = params.toString()
  const path = `/api/admin/ingest/serie-a/${season}/lineups${qs ? `?${qs}` : ''}`
  return adminPostJson<unknown>(path, {}, opts)
}

export async function getFixtureLineups(fixtureId: number): Promise<FixtureLineupsResponse> {
  const base = getApiBase()
  const res = await fetch(`${base}/api/debug/sot/fixture/${fixtureId}/lineups`)
  const body = await res.json().catch(() => ({}))
  if (!res.ok && res.status !== 200) {
    throw new Error(extractErrorMessage(body, res.statusText))
  }
  return body as FixtureLineupsResponse
}

export async function getSportApiFixtureDebug(
  fixtureId: number,
  opts?: AdminRequestOpts,
): Promise<SportApiFixtureDebugResponse> {
  return adminGetJson<SportApiFixtureDebugResponse>(
    `/api/admin/sportapi/debug/fixture/${fixtureId}`,
    { ...opts, timeoutMs: opts?.timeoutMs ?? 90_000 },
  )
}

export async function confirmSportApiMapping(
  fixtureId: number,
  body: {
    provider_event_id: number
    confidence_score?: number | null
    matched_by?: string | null
    raw_payload?: Record<string, unknown> | null
  },
  opts?: AdminRequestOpts,
): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/sportapi/mappings/${fixtureId}/confirm`, body, opts)
}

export async function fetchSportApiLineups(fixtureId: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/sportapi/lineups/${fixtureId}/fetch`, {}, {
    ...opts,
    timeoutMs: opts?.timeoutMs ?? 60_000,
  })
}

export async function getSportApiLineups(
  fixtureId: number,
  includeRaw = false,
  opts?: AdminRequestOpts,
): Promise<SportApiLineupsStoredResponse> {
  const qs = includeRaw ? '?include_raw=true' : ''
  return adminGetJson<SportApiLineupsStoredResponse>(
    `/api/admin/sportapi/lineups/${fixtureId}${qs}`,
    opts,
  )
}

export async function buildPlayerSotProfiles(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/features/player-sot-profiles/serie-a/${season}/build`, {}, opts)
}

export async function getPlayerSotProfilesSummary(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminGetJson<unknown>(`/api/features/player-sot-profiles/serie-a/${season}/summary`, opts)
}
