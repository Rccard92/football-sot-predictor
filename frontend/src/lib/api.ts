/** Client HTTP verso il backend. Base URL da `VITE_API_BASE_URL` (senza trailing slash). */

import type { FixtureLineupsResponse } from '../types/fixtureLineups'
import type { SportApiFixtureDebugResponse, SportApiLineupsStoredResponse } from '../types/sportapi'
import type { FixturePlayerProfilesResponse } from '../types/playerDbProfiles'
import type { SotFixtureExplanationResponse } from '../types/sotExplanation'

export const DEFAULT_SEASON = Number(import.meta.env.VITE_DEFAULT_SEASON) || 2025

export type CompetitionSummary = {
  id: number
  key: string
  name: string
  country: string | null
  provider: string
  provider_league_id: number
  season: number
  timezone: string | null
  is_active: boolean
  is_primary: boolean
  pre_match_cron_enabled: boolean
  status: string | null
  league_id: number | null
  season_id: number | null
}

export type CompetitionDefaultResponse = {
  competition: CompetitionSummary | null
  message?: string | null
}

export type CompetitionBackfillSummary = {
  status: string
  competition_id: number
  competition_key: string
  fixtures_updated: number
  player_profiles_updated: number
  tracked_picks_updated: number
  predictions_updated: number
  team_stats_updated: number
  standings_updated: number
  warnings: string[]
  updated_by_table?: Record<string, number>
}

export async function getCompetitions(): Promise<CompetitionSummary[]> {
  return requestJson<CompetitionSummary[]>('/api/competitions')
}

export async function getDefaultCompetition(): Promise<CompetitionDefaultResponse> {
  return requestJson<CompetitionDefaultResponse>('/api/competitions/default')
}

export async function backfillSerieACompetition(
  season = DEFAULT_SEASON,
): Promise<CompetitionBackfillSummary> {
  return adminPostJson<CompetitionBackfillSummary>(
    `/api/admin/competitions/backfill/serie-a/${season}`,
    {},
  )
}

export async function getNextRoundQuickReportForCompetition(
  competitionId: number,
  opts?: { limit?: number; onlyNextRound?: boolean; modelVersion?: string | null },
): Promise<UpcomingActiveResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  return requestJson<UpcomingActiveResponse>(
    `/api/competitions/${competitionId}/next-round/quick-report${q ? `?${q}` : ''}`,
  )
}

export async function getTrackedBettingPicksForCompetition(
  competitionId: number,
  opts?: { modelVersion?: string },
): Promise<TrackedBettingPicksResponse> {
  const p = new URLSearchParams()
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  return requestJson<TrackedBettingPicksResponse>(
    `/api/competitions/${competitionId}/betting-picks/tracked${q ? `?${q}` : ''}`,
  )
}

export async function getCompetitionDataHealth(
  competitionId: number,
  opts?: { modelVersion?: string },
): Promise<Record<string, unknown>> {
  const p = new URLSearchParams()
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  return adminGetJson<Record<string, unknown>>(
    `/api/admin/data-health/competitions/${competitionId}${q ? `?${q}` : ''}`,
  )
}

export async function postCreateTrackedPicksFromCompetitionRound(
  competitionId: number,
  body?: {
    round?: string
    model_id?: string
    pick_type?: string
    force?: boolean
  },
  opts?: AdminRequestOpts,
): Promise<CreateTrackedPicksFromRoundSummary> {
  return adminPostJson<CreateTrackedPicksFromRoundSummary>(
    `/api/admin/competitions/${competitionId}/betting-picks/create-from-round`,
    body ?? {},
    opts,
  )
}

export type CompetitionDiscoverCandidate = {
  provider_league_id: number
  name: string
  country: string | null
  season: number
  logo?: string | null
  season_current?: boolean | null
  available_seasons?: number[]
  requested_season_available?: boolean
  current_season?: number | null
  raw_payload?: Record<string, unknown> | null
}

export type CompetitionDiscoverResponse = {
  candidates: CompetitionDiscoverCandidate[]
  other_candidates?: CompetitionDiscoverCandidate[]
  ambiguous: boolean
  message?: string | null
  api_query?: string | null
}

export async function discoverCompetitions(body: {
  country: string
  name_query: string
  season: number
}): Promise<CompetitionDiscoverResponse> {
  return adminPostJson<CompetitionDiscoverResponse>('/api/admin/competitions/discover', body)
}

export async function createCompetition(body: Record<string, unknown>): Promise<CompetitionSummary> {
  return adminPostJson<CompetitionSummary>('/api/admin/competitions', body)
}

export async function patchCompetition(
  competitionId: number,
  body: { season?: number; status?: string },
): Promise<CompetitionSummary> {
  return adminPatchJson<CompetitionSummary>(`/api/admin/competitions/${competitionId}`, body)
}

export type SeasonNotAvailableErrorBody = {
  status: 'error'
  code: 'season_not_available'
  message: string
  competition_id: number
  competition_key?: string
  provider_league_id: number
  requested_season: number
  available_seasons: number[]
  league_name?: string | null
  country?: string | null
  suggestion?: string
}

export function isSeasonNotAvailableError(body: unknown): body is SeasonNotAvailableErrorBody {
  return (
    !!body &&
    typeof body === 'object' &&
    (body as SeasonNotAvailableErrorBody).code === 'season_not_available'
  )
}

export const SERIE_A_PROVIDER_LEAGUE_ID = 135

export function isLegacySerieACompetition(comp: CompetitionSummary | null | undefined): boolean {
  if (!comp) return false
  return comp.provider_league_id === SERIE_A_PROVIDER_LEAGUE_ID && comp.country === 'Italy'
}

export async function bootstrapCompetition(
  competitionId: number,
  dryRun = false,
): Promise<Record<string, unknown>> {
  return adminPostJson(`/api/admin/competitions/${competitionId}/ingest/bootstrap`, { dry_run: dryRun })
}

export async function ingestCompetitionTeamStats(
  competitionId: number,
  dryRun = false,
): Promise<Record<string, unknown>> {
  return adminPostJson(`/api/admin/competitions/${competitionId}/ingest/team-stats`, { dry_run: dryRun })
}

export async function ingestCompetitionPlayerStats(
  competitionId: number,
  dryRun = false,
): Promise<Record<string, unknown>> {
  return adminPostJson(`/api/admin/competitions/${competitionId}/ingest/player-match-stats`, {
    dry_run: dryRun,
  })
}

export async function buildCompetitionPlayerProfiles(
  competitionId: number,
  dryRun = false,
): Promise<Record<string, unknown>> {
  return adminPostJson(
    `/api/admin/competitions/${competitionId}/features/player-season-profiles/build`,
    { dry_run: dryRun },
  )
}

export async function refreshCompetitionNextRound(
  competitionId: number,
  dryRun = false,
  opts?: { modelVersion?: string; generateMode?: 'default' | 'v21_only' | 'v20_v21_comparison' },
): Promise<Record<string, unknown>> {
  const body: Record<string, unknown> = { dry_run: dryRun }
  if (opts?.modelVersion) body.model_version = opts.modelVersion
  if (opts?.generateMode) body.generate_mode = opts.generateMode
  return adminPostJson(`/api/admin/competitions/${competitionId}/refresh/next-round`, body)
}

export type ModelComparisonSide = {
  model_version?: string
  predicted_total_sot?: number | null
  home_sot?: number | null
  away_sot?: number | null
  statistical_pick?: string | null
  cautious_pick?: string | null
  statistical_margin?: number | null
  cautious_margin?: number | null
  statistical_risk?: string | null
  confidence_label?: string | null
}

export type ModelComparisonDelta = {
  total_sot?: number | null
  home_sot?: number | null
  away_sot?: number | null
  direction?: 'up' | 'down' | 'stable' | string | null
  pick_changed?: boolean
  confidence_changed?: boolean
}

export type ModelComparisonRow = {
  fixture_id: number
  api_fixture_id?: number
  kickoff_at?: string | null
  round?: string | null
  status_short?: string | null
  home_team: { id: number; name: string; logo_url?: string | null }
  away_team: { id: number; name: string; logo_url?: string | null }
  v20?: ModelComparisonSide | null
  v21?: ModelComparisonSide | null
  delta?: ModelComparisonDelta | null
  lineup_status?: LineupStatusPayload | string | null
}

export type ModelComparisonResponse = {
  status?: string
  message?: string
  competition_id?: number
  competition_name?: string
  competition_key?: string
  season?: number
  round?: string | null
  base_model?: { model_version: string; label: string; response_key?: string }
  compare_model?: { model_version: string; label: string; response_key?: string }
  matches_count?: number
  rows: ModelComparisonRow[]
  missing?: {
    base_model_missing_predictions?: number
    compare_model_missing_predictions?: number
  }
  warnings?: string[]
}

export async function getNextRoundModelComparison(
  competitionId: number,
  opts?: {
    limit?: number
    onlyNextRound?: boolean
    baseModel?: string
    compareModel?: string
  },
): Promise<ModelComparisonResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  if (opts?.baseModel) p.set('base_model', opts.baseModel)
  if (opts?.compareModel) p.set('compare_model', opts.compareModel)
  const q = p.toString()
  return requestJson<ModelComparisonResponse>(
    `/api/competitions/${competitionId}/next-round/model-comparison${q ? `?${q}` : ''}`,
  )
}

/** Generazione previsioni v2.1 Weighted Components (engine autonomo). */
export async function postGenerateV21WeightedComponents(
  season: number,
  opts?: AdminRequestOpts & { fixtureId?: number; competitionId?: number },
): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 300_000
  const p = new URLSearchParams()
  if (opts?.fixtureId != null) p.set('fixture_id', String(opts.fixtureId))
  if (opts?.competitionId != null) p.set('competition_id', String(opts.competitionId))
  const q = p.toString()
  return requestPostJsonWithOpts<unknown>(
    `/api/predictions/sot/serie-a/${season}/generate-v21-weighted-components${q ? `?${q}` : ''}`,
    {},
    { ...opts, timeoutMs },
  )
}

export type SportApiCompetitionLineupsIngestOpts = {
  scope?: 'next_round' | 'upcoming_limit' | 'fixture_ids'
  dryRun?: boolean
  force?: boolean
  regenerateV20?: boolean
  upcomingLimit?: number
  fixtureIds?: number[]
  timeoutMs?: number
}

export type SportApiCompetitionLineupsResultRow = {
  fixture_id: number
  api_fixture_id?: number
  match_api_sports?: string
  kickoff?: string
  recommendation?: string
  would_save?: boolean
  sportapi_event_id?: number | null
  confidence?: number | null
  reason?: string | null
  status?: string
  error?: string | null
  lineups_ok?: boolean
  v20_regenerated?: boolean
}

export type SportApiCompetitionLineupsIngestSummary = {
  status: string
  message?: string
  competition_id: number
  competition_name?: string
  scope?: string
  round?: string | null
  dry_run?: boolean
  fixtures_checked: number
  mappings_found: number
  mappings_uncertain: number
  mappings_saved: number
  lineups_would_fetch: number
  lineups_imported: number
  missing_players_imported: number
  predictions_regenerated: number
  estimated_api_calls: number
  skipped_recent?: number
  failed?: number
  warnings?: string[]
  results?: SportApiCompetitionLineupsResultRow[]
}

export async function postCompetitionSportApiLineupsIngest(
  competitionId: number,
  opts: SportApiCompetitionLineupsIngestOpts = {},
): Promise<SportApiCompetitionLineupsIngestSummary> {
  const body = {
    scope: opts.scope ?? 'next_round',
    dry_run: opts.dryRun ?? true,
    force: opts.force ?? false,
    regenerate_v20: opts.regenerateV20 ?? true,
    upcoming_limit: opts.upcomingLimit ?? 20,
    fixture_ids: opts.fixtureIds ?? null,
  }
  return adminPostJson<SportApiCompetitionLineupsIngestSummary>(
    `/api/admin/competitions/${competitionId}/ingest/sportapi-lineups`,
    body,
    { timeoutMs: opts.timeoutMs ?? 600_000 },
  )
}

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

/** Rigenera previsioni v2.0 per una singola fixture (dopo aggiornamento formazione SportAPI). */
export async function postRegenerateV20ForFixture(
  season: number,
  fixtureId: number,
  opts?: AdminRequestOpts,
): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 120_000
  return requestPostJsonWithOpts<unknown>(
    `/api/predictions/sot/serie-a/${season}/fixture/${fixtureId}/regenerate-v20`,
    {},
    { ...opts, timeoutMs },
  )
}

/** Generazione previsioni v2.0 Lineup Impact (base v1.1 × fattori formazione, solo DB). */
export async function postGenerateV20LineupImpactUpcoming(
  season: number,
  opts?: AdminRequestOpts & { fixtureId?: number },
): Promise<unknown> {
  const timeoutMs = opts?.timeoutMs ?? 300_000
  const p = opts?.fixtureId != null ? `?fixture_id=${opts.fixtureId}` : ''
  return requestPostJsonWithOpts<unknown>(
    `/api/predictions/sot/serie-a/${season}/generate-v20-lineup-impact${p}`,
    {},
    { ...opts, timeoutMs },
  )
}

export async function postRefreshNextRoundSportApiLineups(
  season: number,
  opts?: AdminRequestOpts & { force?: boolean; syncSquads?: boolean; regenerateV20?: boolean },
): Promise<SportApiRoundRefreshSummary> {
  const p = new URLSearchParams()
  if (opts?.force) p.set('force', 'true')
  if (opts?.syncSquads) p.set('sync_squads', 'true')
  if (opts?.regenerateV20) p.set('regenerate_v20', 'true')
  const q = p.toString()
  return adminPostJson<SportApiRoundRefreshSummary>(
    `/api/admin/sportapi/lineups/serie-a/${season}/next-round/refresh${q ? `?${q}` : ''}`,
    {},
    opts,
  )
}

export async function postSyncNextRoundApiSquadsBatch(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/sportapi/serie-a/${season}/sync-api-squads-batch`, {}, opts)
}

export type PreMatchJobResultRow = {
  fixture_id: number
  match?: string
  match_name?: string
  kickoff?: string | null
  sportapi_event_id?: number | null
  confirmed?: boolean
  before_total_sot?: number | null
  after_total_sot?: number | null
  delta_total_sot?: number | null
  monitoring_pick_status?: string
  status?: string
  error?: string
}

export type PreMatchJobSummary = {
  status: string
  season?: number
  message?: string
  checked_fixtures?: number
  eligible_fixtures?: number
  refreshed: number
  skipped_recent?: number
  skipped_no_mapping?: number
  updated_monitoring_picks?: number
  created_monitoring_picks?: number
  checked: number
  picks_created: number
  picks_updated: number
  skipped: number
  mapping_missing?: number
  lineup_confirmed?: number
  minutes_before?: number
  window_minutes?: number
  errors: { fixture_id?: number; error?: string }[]
  results?: PreMatchJobResultRow[]
}

export type TrackedBettingPickRow = {
  id: number
  fixture_id: number
  kickoff_at: string | null
  match_name: string
  home_team_name: string
  away_team_name: string
  home_team: UpcomingMatchTeam
  away_team: UpcomingMatchTeam
  initial_predicted_total_sot: number | null
  official_predicted_total_sot: number | null
  initial_suggested_pick: string | null
  initial_line_value: number | null
  initial_odd: number | null
  official_suggested_pick: string | null
  official_line_value: number | null
  official_odd: number | null
  result_home_sot: number | null
  result_away_sot: number | null
  result_total_sot: number | null
  sot_display?: string
  sot_unavailable_reason?: string | null
  fixture_status: string | null
  elapsed: number | null
  fixture_status_label: string
  initial_outcome: string
  official_outcome: string
  model_id?: string
  model_version?: string
  is_live_fixture?: boolean
  status?: string
}

export type TrackedBettingPicksSummary = {
  total: number
  live: number
  initial_won: number
  initial_lost: number
  official_won: number
  official_lost: number
  initial_win_rate: number | null
  official_win_rate: number | null
}

export type TrackedBettingPicksResponse = {
  status: string
  season: number
  picks: TrackedBettingPickRow[]
  count: number
  summary?: TrackedBettingPicksSummary
}

export type CreateTrackedPicksFromRoundSummary = {
  status: string
  season: number
  model_id?: string
  pick_type?: string
  fixtures_total: number
  created: number
  updated: number
  skipped: number
  errors: { fixture_id?: number; match?: string; error?: string }[]
  warnings: string[]
}

export type StatsDebugEntry = {
  pick_id: number
  fixture_id: number
  api_fixture_id: number
  fixture_status?: string
  statistics_found?: boolean
  raw_statistics_sample?: string
  extracted_home_sot?: number | null
  extracted_away_sot?: number | null
  extraction_error?: string | null
  metric_labels_seen?: string[]
  metric_label_home?: string | null
  metric_label_away?: string | null
}

export type TrackedPicksRefreshResultsSummary = {
  status: string
  season?: number
  competition_id?: number
  competition_key?: string
  scope?: 'all' | 'live' | 'unfinished' | 'unfinished_or_recent'
  force?: boolean
  last_refreshed_at?: string
  picks_checked?: number
  picks_updated?: number
  tracked_checked?: number
  updated?: number
  api_calls?: number
  errors: { pick_id?: number; error?: string }[]
  stats_debug?: StatsDebugEntry[]
}

export type RefereeSyncFixtureResponse = {
  status: string
  fixture_id?: number
  api_fixture_id?: number
  match?: string
  referee?: string | null
  referee_id?: number
  saved?: boolean
  reason?: string
  message?: string
}

export type RefereeProfileResponse = {
  status: string
  profile_label?: string
  referee_name?: string
  referee_id?: number | null
  league_id?: number
  season?: number
  matches_count?: number
  last_matches_count?: number
  total_yellow_cards?: number
  total_red_cards?: number
  avg_yellow_cards?: number | null
  avg_red_cards?: number | null
  severity_label?: string | null
  sample_quality?: string | null
  data_source?: 'db_only' | 'api_sports_fetched' | 'mixed'
  coverage_note?: string
  fixtures_scanned?: number
  fixtures_with_same_referee?: number
  fixtures_with_card_data?: number
  missing_card_data_count?: number
  match_warning?: string
  message?: string
  saved?: boolean
  fixtures_used?: unknown[]
}

export type RefereeImportSeasonResponse = {
  status: string
  referee_name?: string
  referee_id?: number
  league_id?: number
  season?: number
  fixtures_scanned?: number
  referee_matches_found?: number
  fixtures_imported?: number
  card_data_found?: number
  api_fetches_used?: number
  match_warning?: string
  message?: string
  errors?: { api_fixture_id?: string; error?: string }[]
}

export type RefereeContextBlock = {
  available: boolean
  label?: string
  message?: string
  matches_count?: number
  avg_yellow_cards?: number | null
  avg_red_cards?: number | null
  avg_yellow_team?: number | null
  avg_red_team?: number | null
  severity_label?: string | null
  sample_quality?: string | null
  data_source?: string
}

export type RefereeMatchContextResponse = {
  status: string
  fixture?: string
  fixture_id?: number
  referee?: string
  message?: string
  home_team_context?: RefereeContextBlock
  away_team_context?: RefereeContextBlock
  direct_h2h_context?: RefereeContextBlock
}

export async function postRefereeSyncFixture(
  body: { fixture_id: number } | { api_fixture_id: number },
  opts?: AdminRequestOpts,
): Promise<RefereeSyncFixtureResponse> {
  return adminPostJson<RefereeSyncFixtureResponse>('/api/admin/referees/sync-fixture', body, opts)
}

export async function postRefereeProfile(
  body: {
    referee_name?: string
    league_id?: number
    season?: number
    fixture_id?: number
    max_matches?: number
  },
  opts?: AdminRequestOpts,
): Promise<RefereeProfileResponse> {
  return adminPostJson<RefereeProfileResponse>('/api/admin/referees/profile', body, {
    timeoutMs: 300_000,
    ...opts,
  })
}

export async function postRefereeImportSeasonHistory(
  body: { referee_name: string; league_id?: number; season: number },
  opts?: AdminRequestOpts,
): Promise<RefereeImportSeasonResponse> {
  return adminPostJson<RefereeImportSeasonResponse>(
    '/api/admin/referees/import-season-history',
    body,
    { timeoutMs: 600_000, ...opts },
  )
}

export async function postRefereeRecentHistory(
  body: { referee_name: string; limit?: number },
  opts?: AdminRequestOpts,
): Promise<RefereeProfileResponse> {
  return adminPostJson<RefereeProfileResponse>('/api/admin/referees/recent-history', body, opts)
}

export async function postRefereeMatchContext(
  body: { fixture_id: number },
  opts?: AdminRequestOpts,
): Promise<RefereeMatchContextResponse> {
  return adminPostJson<RefereeMatchContextResponse>('/api/admin/referees/match-context', body, opts)
}

/** Job pre-match da Admin UI: stessa chiamata degli altri endpoint admin (senza CRON_SECRET nel frontend). */
export async function postPreMatchOfficialLineupRefreshJob(
  body: { force?: boolean; minutes_before?: number; window_minutes?: number; season?: number } = {},
  opts?: AdminRequestOpts,
): Promise<PreMatchJobSummary> {
  return adminPostJson<PreMatchJobSummary>(
    '/api/admin/jobs/pre-match-official-lineups/run',
    body,
    { timeoutMs: 600_000, ...opts },
  )
}

/** @deprecated Usare postPreMatchOfficialLineupRefreshJob */
export async function postPreMatchLineupRefreshJob(
  body: { force?: boolean; minutes_before?: number; window_minutes?: number; season?: number } = {},
  opts?: AdminRequestOpts,
): Promise<PreMatchJobSummary> {
  return postPreMatchOfficialLineupRefreshJob(body, opts)
}

export async function getTrackedBettingPicks(season: number): Promise<TrackedBettingPicksResponse> {
  return requestJson<TrackedBettingPicksResponse>(`/api/betting-picks/serie-a/${season}/tracked`)
}

/** @deprecated Usare postRefreshTrackedPickResultsForCompetition con competition_id */
export async function postRefreshTrackedPickResults(
  season: number,
  body?: { scope?: 'all' | 'live' | 'unfinished' | 'unfinished_or_recent'; force?: boolean },
  opts?: AdminRequestOpts,
): Promise<TrackedPicksRefreshResultsSummary> {
  return adminPostJson<TrackedPicksRefreshResultsSummary>(
    `/api/admin/betting-picks/serie-a/${season}/refresh-results`,
    body ?? {},
    opts,
  )
}

export async function postRefreshTrackedPickResultsForCompetition(
  competitionId: number,
  body?: {
    scope?: 'all' | 'live' | 'unfinished' | 'unfinished_or_recent'
    force?: boolean
    model_version?: string
  },
  opts?: AdminRequestOpts,
): Promise<TrackedPicksRefreshResultsSummary> {
  return adminPostJson<TrackedPicksRefreshResultsSummary>(
    `/api/admin/competitions/${competitionId}/betting-picks/refresh-results`,
    body ?? {},
    opts,
  )
}

export async function postCreateTrackedPicksFromRound(
  season: number,
  body?: {
    round?: string
    model_id?: string
    pick_type?: string
    force?: boolean
  },
  opts?: AdminRequestOpts,
): Promise<CreateTrackedPicksFromRoundSummary> {
  return adminPostJson<CreateTrackedPicksFromRoundSummary>(
    `/api/admin/betting-picks/serie-a/${season}/create-from-round`,
    body ?? {},
    opts,
  )
}

export type OddsBookmakerRow = {
  id: number
  provider: string
  provider_bookmaker_id: number
  name: string
  is_selected: boolean
  is_active: boolean
  last_synced_at: string | null
}

export type AdminBookmakersListResponse = {
  status: string
  total: number
  last_synced_at: string | null
  bookmakers: OddsBookmakerRow[]
}

export type BookmakersSyncSummary = {
  status: string
  fetched_count: number
  created_count: number
  updated_count: number
  skipped_count?: number
  total_saved: number
  last_synced_at: string
  errors: string[]
}

export async function getAdminBookmakers(): Promise<AdminBookmakersListResponse> {
  return adminGetJson<AdminBookmakersListResponse>('/api/admin/bookmakers')
}

export async function postSyncBookmakers(opts?: AdminRequestOpts): Promise<BookmakersSyncSummary> {
  return adminPostJson<BookmakersSyncSummary>('/api/admin/bookmakers/sync', {}, opts)
}

export type SportApiNormalizedMarket = {
  source: string
  provider_id: number
  market_name: string | null
  bookmaker_name: string | null
  outcome_name: string | null
  line: string | null
  price: string | null
  status: string | null
}

export type SportApiOddsDiscoveryComparison = {
  api_sports_bookmakers_total: number
  sportapi_markets_on_event: number
  sportapi_bookmakers_deduced: number | null
  note: string
}

export type SportApiOddsDiscoveryResponse = {
  status: string
  message?: string
  provider?: string
  fixture_id?: number | null
  api_fixture_id?: number | null
  sportapi_event_id?: number
  provider_id?: number
  markets_count?: number
  bookmakers_count?: number | null
  raw_payload?: unknown
  normalized_markets?: SportApiNormalizedMarket[]
  snapshot_id?: number | null
  comparison?: SportApiOddsDiscoveryComparison
}

export async function postSportApiOddsDiscovery(
  body: {
    fixture_id?: number | null
    api_fixture_id?: number | null
    sportapi_event_id?: number | null
    provider_id?: number
    save_snapshot?: boolean
  },
  opts?: AdminRequestOpts,
): Promise<SportApiOddsDiscoveryResponse> {
  return adminPostJson<SportApiOddsDiscoveryResponse>(
    '/api/admin/bookmakers/sportapi/odds-discovery',
    body,
    opts,
  )
}

export const SPORTAPI_DEFAULT_PROVIDER_SLUG = 'sisal-italy-affiliate'

export type SportApiOddsProviderRow = {
  id: number
  provider_slug: string
  provider_name: string
  provider_country: string | null
  provider_id: number | null
  odds_from_id: number | null
  odds_from_slug: string | null
  odds_from_name: string | null
  live_odds_from_id: number | null
  working_odds_provider_id: number | null
  is_selected: boolean
  is_active: boolean
  last_synced_at: string | null
}

export type SportApiProvidersListResponse = {
  status: string
  total: number
  last_synced_at: string | null
  providers: SportApiOddsProviderRow[]
}

export type SportApiProvidersSyncSummary = {
  status: string
  country: string
  channel: string
  fetched: number
  created: number
  updated: number
  skipped: number
  total_in_db: number
}

export type SportApiProviderDetailResponse = {
  status: string
  provider: SportApiOddsProviderRow & {
    live_odds_from_slug?: string | null
    live_odds_from_name?: string | null
    default_bet_slip_link?: string | null
    primary_color?: string | null
  }
  raw?: unknown
}

export type SportApi1x2NormalizationStatus = 'ok' | 'incomplete' | 'not_found'

export type SportApi1x2Normalized = {
  market_found: boolean
  market_matched?: boolean
  outcomes_complete?: boolean
  normalization_status?: SportApi1x2NormalizationStatus
  market_key: string
  market_name_original: string | null
  home_odd: number | null
  draw_odd: number | null
  away_odd: number | null
  home_label?: string | null
  draw_label?: string | null
  away_label?: string | null
  home_odd_raw?: unknown
  draw_odd_raw?: unknown
  away_odd_raw?: unknown
  provider_id?: number | null
  provider_slug?: string | null
  available_markets?: string[]
  raw_market?: unknown
  debug_full_time_market?: unknown
}

export type SportApiOddsTestEventResponse = {
  status: string
  message?: string
  sportapi_event_id: number
  provider_slug: string
  working_provider_id?: number
  candidate_provider_ids?: number[]
  attempts?: { provider_id: number; status: string; message?: string }[]
  normalized_1x2?: SportApi1x2Normalized
  snapshot_id?: number | null
  raw_available?: boolean
}

export type SportApiNextRound1x2Row = {
  fixture_id: number
  api_fixture_id: number | null
  kickoff_at: string | null
  match_label: string
  sportapi_event_id: number | null
  provider_id_used: number | null
  status: string
  market_found?: boolean | null
  outcomes_complete?: boolean | null
  normalization_status?: SportApi1x2NormalizationStatus | null
  home_odd: number | null
  draw_odd: number | null
  away_odd: number | null
  available_markets?: string[]
  error?: string | null
}

export type SportApiNextRound1x2Response = {
  status: string
  message?: string
  provider_slug: string
  working_provider_id?: number | null
  candidate_provider_ids?: number[]
  total_fixtures: number
  processed: number
  skipped_no_mapping: number
  errors: string[]
  rows: SportApiNextRound1x2Row[]
}

export async function getSportApiProviders(): Promise<SportApiProvidersListResponse> {
  return adminGetJson<SportApiProvidersListResponse>('/api/admin/bookmakers/sportapi/providers')
}

export async function postSyncSportApiProviders(
  body?: { country?: string; channel?: string },
  opts?: AdminRequestOpts,
): Promise<SportApiProvidersSyncSummary> {
  return adminPostJson<SportApiProvidersSyncSummary>(
    '/api/admin/bookmakers/sportapi/providers/sync',
    body ?? {},
    opts,
  )
}

export async function postSyncSportApiProviderDetail(
  slug: string,
  opts?: AdminRequestOpts,
): Promise<SportApiProviderDetailResponse> {
  return adminPostJson<SportApiProviderDetailResponse>(
    `/api/admin/bookmakers/sportapi/providers/${encodeURIComponent(slug)}/sync-detail`,
    {},
    opts,
  )
}

export async function postSportApiOddsTestEvent(
  body: {
    sportapi_event_id: number
    provider_slug?: string
    provider_id?: number | null
    save_snapshot?: boolean
  },
  opts?: AdminRequestOpts,
): Promise<SportApiOddsTestEventResponse> {
  return adminPostJson<SportApiOddsTestEventResponse>(
    '/api/admin/bookmakers/sportapi/odds/test-event',
    body,
    opts,
  )
}

export async function postSportApiNextRound1x2(
  body?: { provider_slug?: string; force?: boolean; season_year?: number },
  opts?: AdminRequestOpts,
): Promise<SportApiNextRound1x2Response> {
  return adminPostJson<SportApiNextRound1x2Response>(
    '/api/admin/bookmakers/sportapi/odds/next-round-1x2',
    body ?? {},
    { ...opts, timeoutMs: opts?.timeoutMs ?? 300_000 },
  )
}

export type SportApiEventOddsOutcome = {
  name?: string | null
  price?: number | null
  line?: number | null
  status?: string | null
  raw?: unknown
}

export type SportApiEventOddsMarket = {
  market_name: string
  market_id?: string | null
  market_group?: string | null
  choice_group?: string | null
  period?: string | null
  market_key_guess?: string | null
  line?: number | null
  outcomes: SportApiEventOddsOutcome[]
  outcomes_count: number
  status?: string | null
  raw_market?: unknown
}

export type SportApiSotCandidateMarket = {
  market_name: string
  market_id?: string | null
  line?: number | null
  match_reason?: string
  mapping_confidence?: 'high' | 'medium' | 'low'
  suggested_market_key?: string | null
  over_odd?: number | null
  under_odd?: number | null
  outcomes_count?: number
}

export type SportApiMarketsDiscoveryResponse = {
  status: string
  message?: string
  sportapi_event_id: number
  provider_slug: string
  working_provider_id?: number
  candidate_provider_ids?: number[]
  markets_count: number
  sot_candidates_count?: number
  normalized_markets: SportApiEventOddsMarket[]
  sot_candidate_markets: SportApiSotCandidateMarket[]
  raw_payload?: unknown
}

export type SportApiMarketMappingRow = {
  id: number
  provider_slug: string
  provider_id_used?: number | null
  raw_market_name: string
  raw_market_id?: string | null
  normalized_market_key: string
  confidence: string
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export type SportApiMarketMappingsResponse = {
  status: string
  count: number
  mappings: SportApiMarketMappingRow[]
}

export type SportApiNextRoundSotRow = {
  fixture_id: number
  kickoff_at: string | null
  match_label: string
  sportapi_event_id: number | null
  provider_id_used: number | null
  market_name: string | null
  line: number | null
  over_odd: number | null
  under_odd: number | null
  status: string
}

export type SportApiNextRoundSotResponse = {
  status: string
  message?: string
  provider_slug: string
  market_key?: string
  mappings_count: number
  total_fixtures: number
  rows: SportApiNextRoundSotRow[]
  errors?: string[]
}

export async function postSportApiMarketsDiscovery(
  body: {
    sportapi_event_id: number
    provider_slug?: string
    provider_id?: number | null
  },
  opts?: AdminRequestOpts,
): Promise<SportApiMarketsDiscoveryResponse> {
  return adminPostJson<SportApiMarketsDiscoveryResponse>(
    '/api/admin/bookmakers/sportapi/odds/markets-discovery',
    body,
    { ...opts, timeoutMs: opts?.timeoutMs ?? 90_000 },
  )
}

export async function getSportApiMarketMappings(
  providerSlug?: string,
): Promise<SportApiMarketMappingsResponse> {
  const q = providerSlug ? `?provider_slug=${encodeURIComponent(providerSlug)}` : ''
  return adminGetJson<SportApiMarketMappingsResponse>(
    `/api/admin/bookmakers/sportapi/odds/market-mappings${q}`,
  )
}

export async function postSportApiMarketMapping(
  body: {
    provider_slug?: string
    raw_market_name: string
    normalized_market_key: string
    provider_id_used?: number | null
    raw_market_id?: string | null
    confidence?: string
    sample_raw_market?: unknown
  },
): Promise<{ status: string; mapping: SportApiMarketMappingRow }> {
  return adminPostJson('/api/admin/bookmakers/sportapi/odds/market-mappings', body)
}

export async function patchDeactivateSportApiMarketMapping(
  mappingId: number,
): Promise<{ status: string; id: number; is_active: boolean }> {
  return adminPatchJson<{ status: string; id: number; is_active: boolean }>(
    `/api/admin/bookmakers/sportapi/odds/market-mappings/${mappingId}/deactivate`,
    {},
  )
}

export async function postSportApiNextRoundSot(
  body?: { provider_slug?: string; season_year?: number; market_key?: string; limit?: number },
  opts?: AdminRequestOpts,
): Promise<SportApiNextRoundSotResponse> {
  return adminPostJson<SportApiNextRoundSotResponse>(
    '/api/admin/bookmakers/sportapi/odds/next-round-sot',
    body ?? {},
    { ...opts, timeoutMs: opts?.timeoutMs ?? 300_000 },
  )
}

export type SportApiScanSotProviderRow = {
  provider_name: string
  provider_slug: string
  working_provider_id: number | null
  markets_count: number
  has_sot_market: boolean
  sot_candidate_markets: SportApiSotCandidateMarket[]
  status: string
  error: string | null
  raw_payload?: unknown
}

export type SportApiScanSotProvidersResponse = {
  status: string
  scan_status?: string
  sportapi_event_id: number
  country: string
  providers_in_db?: number
  providers_matching_country?: number
  providers_scanned: number
  providers_with_odds: number
  providers_with_sot: number
  providers_errors: number
  rows: SportApiScanSotProviderRow[]
  message?: string | null
}

export async function postSportApiScanSotProviders(
  body: {
    sportapi_event_id: number
    country?: string
    channel?: string
    max_providers?: number | null
    provider_slug?: string | null
    save_snapshot?: boolean
    auto_sync_if_empty?: boolean
  },
  opts?: AdminRequestOpts,
): Promise<SportApiScanSotProvidersResponse> {
  return adminPostJson<SportApiScanSotProvidersResponse>(
    '/api/admin/bookmakers/sportapi/odds/scan-sot-providers',
    body,
    { ...opts, timeoutMs: opts?.timeoutMs ?? 300_000 },
  )
}

/** GET admin/diagnostica con timeout opzionale. */
export async function getModelStatusWithOpts(season: number, opts?: AdminRequestOpts): Promise<ModelStatusResponse> {
  return requestJsonWithOpts<ModelStatusResponse>(
    `/api/predictions/sot/serie-a/${season}/model-status`,
    { ...opts, timeoutMs: opts?.timeoutMs ?? 60_000 },
  )
}

export async function getModelStatusForCompetition(
  competitionId: number,
  opts?: AdminRequestOpts & { modelVersion?: string | null },
): Promise<ModelStatusResponse> {
  const p = new URLSearchParams()
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  return requestJsonWithOpts<ModelStatusResponse>(
    `/api/competitions/${competitionId}/model-status${q ? `?${q}` : ''}`,
    { ...opts, timeoutMs: opts?.timeoutMs ?? 60_000 },
  )
}

export async function resolveModelStatus(
  comp: CompetitionSummary | null | undefined,
  fallbackSeason: number,
  opts?: AdminRequestOpts,
): Promise<ModelStatusResponse | null> {
  if (!comp) return null
  if (isLegacySerieACompetition(comp)) {
    return getModelStatusWithOpts(comp.season ?? fallbackSeason, opts)
  }
  return getModelStatusForCompetition(comp.id, opts)
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

/** PATCH admin generici. */
export async function adminPatchJson<T>(path: string, body: unknown = {}, opts?: AdminRequestOpts): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  let cancelTimeout: (() => void) | undefined
  let signal: AbortSignal | undefined = opts?.signal
  const timeoutMs = opts?.timeoutMs ?? 90_000
  if (timeoutMs > 0) {
    const x = createLinkedTimeoutSignal(timeoutMs, opts?.signal)
    signal = x.signal
    cancelTimeout = x.cancel
  }
  try {
    const res = await fetch(`${base}${p}`, {
      method: 'PATCH',
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

// --- Backtest Engine (Step C / C.1) ---

export type BacktestDebugHealthResponse = {
  status: string
  tables: Record<string, boolean>
  runs_count: number
  predictions_count: number
  picks_count: number
  metrics_count: number
  markets: { market_key: string; status: string }[]
  algorithms: { market_key: string; algorithm_version: string; status: string }[]
  active_markets: string[]
  planned_markets: string[]
  active_algorithms: string[]
}

export type BacktestRunCreateBody = {
  competition_id: number
  season_year?: number | null
  season_id?: number | null
  market_key: string
  algorithm_version: string
  mode: string
  fixture_scope: string
  date_from?: string | null
  date_to?: string | null
  config_json?: Record<string, unknown> | null
  model_manifest_version?: string | null
}

export type BacktestRunRow = {
  id: number
  competition_id: number
  competition_name?: string | null
  season_year?: number | null
  market_key: string
  algorithm_version: string
  mode: string
  fixture_scope: string
  status: string
  created_at: string
  completed_at?: string | null
  summary_json?: Record<string, unknown> | null
}

export type BacktestRunListResponse = {
  items: BacktestRunRow[]
  total: number
  limit: number
  offset: number
}

export type BacktestRunDetail = BacktestRunRow & {
  season_id?: number | null
  date_from?: string | null
  date_to?: string | null
  config_json?: Record<string, unknown>
  summary_json?: Record<string, unknown> | null
  error_json?: Record<string, unknown> | null
  algorithm_config_hash?: string
  model_manifest_version?: string | null
  git_commit_sha?: string | null
  predictions_count: number
  picks_count: number
  metrics_count: number
}

export type BacktestApiRawResponse = {
  status: number
  body: unknown
}

export function getBacktestErrorCode(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  const o = body as Record<string, unknown>
  const detail = o.detail
  if (detail && typeof detail === 'object' && detail !== null) {
    const code = (detail as Record<string, unknown>).code
    if (typeof code === 'string') return code
  }
  return null
}

export function getBacktestErrorMessage(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null
  const o = body as Record<string, unknown>
  const detail = o.detail
  if (detail && typeof detail === 'object' && detail !== null) {
    const msg = (detail as Record<string, unknown>).message
    if (typeof msg === 'string') return msg
  }
  if (typeof detail === 'string') return detail
  return null
}

export async function fetchBacktestApiRaw(
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
): Promise<BacktestApiRawResponse> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const init: RequestInit = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (method === 'POST') {
    init.body = JSON.stringify(body ?? {})
  }
  const res = await fetch(`${base}${p}`, init)
  const ct = res.headers.get('content-type') ?? ''
  let parsed: unknown = null
  if (ct.includes('application/json')) {
    try {
      parsed = await res.json()
    } catch {
      parsed = null
    }
  }
  return { status: res.status, body: parsed }
}

export async function getBacktestDebugHealth(): Promise<BacktestDebugHealthResponse> {
  return requestJson<BacktestDebugHealthResponse>('/api/backtest/debug/health')
}

export async function createBacktestRun(body: BacktestRunCreateBody): Promise<BacktestRunRow> {
  return requestPostJson<BacktestRunRow>('/api/backtest/runs', body)
}

export async function listBacktestRuns(params?: {
  competition_id?: number
  season_year?: number
  market_key?: string
  algorithm_version?: string
  mode?: string
  status?: string
  limit?: number
  offset?: number
}): Promise<BacktestRunListResponse> {
  const q = new URLSearchParams()
  if (params?.competition_id != null) q.set('competition_id', String(params.competition_id))
  if (params?.season_year != null) q.set('season_year', String(params.season_year))
  if (params?.market_key) q.set('market_key', params.market_key)
  if (params?.algorithm_version) q.set('algorithm_version', params.algorithm_version)
  if (params?.mode) q.set('mode', params.mode)
  if (params?.status) q.set('status', params.status)
  if (params?.limit != null) q.set('limit', String(params.limit))
  if (params?.offset != null) q.set('offset', String(params.offset))
  const qs = q.toString()
  return requestJson<BacktestRunListResponse>(`/api/backtest/runs${qs ? `?${qs}` : ''}`)
}

export async function getBacktestRun(runId: number): Promise<BacktestRunDetail> {
  return requestJson<BacktestRunDetail>(`/api/backtest/runs/${runId}`)
}

// --- Backtest Engine Step D (PointInTimeContext) ---

export type BacktestFixtureCandidate = {
  fixture_id: number
  kickoff_at: string
  round?: string | null
  status: string
  home_team: { id: number; name: string }
  away_team: { id: number; name: string }
  has_team_stats: boolean
  actual_total_sot?: number | null
}

export type BacktestFixtureListResponse = {
  items: BacktestFixtureCandidate[]
  total: number
  limit: number
  offset: number
}

export type TeamPointInTimeStats = {
  team_id: number
  team_name: string
  avg_sot_for?: number | null
  avg_sot_against?: number | null
  avg_total_shots_for?: number | null
  avg_total_shots_against?: number | null
  avg_xg_for?: number | null
  avg_xg_against?: number | null
  sample_count: number
  latest_fixture_used_at?: string | null
  last5?: {
    last5_avg_sot_for?: number | null
    last5_avg_sot_against?: number | null
    last5_avg_xg_for?: number | null
    last5_avg_xg_against?: number | null
    last5_count: number
    status: string
  }
}

export type PointInTimeContextResponse = {
  competition_id: number
  competition_key: string
  competition_name: string
  fixture_id: number
  fixture_kickoff_at: string
  fixture_round?: string | null
  fixture_status: string
  home_team_id: number
  home_team_name: string
  away_team_id: number
  away_team_name: string
  mode: string
  market_key: string
  cutoff_time: string
  leakage_guard: boolean
  latest_fixture_used_at?: string | null
  prior_fixtures_count: number
  home_prior_matches_count: number
  away_prior_matches_count: number
  league_prior_matches_count: number
  home_team_stats: TeamPointInTimeStats
  away_team_stats: TeamPointInTimeStats
  league_baselines: {
    league_avg_sot_for?: number | null
    league_avg_sot_against?: number | null
    league_avg_total_shots?: number | null
    league_avg_xg_for?: number | null
    league_avg_xg_conceded?: number | null
    sample_count: number
    latest_fixture_used_at?: string | null
  }
  actuals_for_scoring: {
    actual_home_sot?: number | null
    actual_away_sot?: number | null
    actual_total_sot?: number | null
    final_score?: string | null
    fixture_status?: string | null
  }
  actuals_used_as_input: boolean
  warnings: string[]
  feature_snapshot_json: Record<string, unknown>
}

export async function listBacktestDebugFixtures(params: {
  competition_id: number
  season_year?: number
  status?: string
  limit?: number
  offset?: number
  round_contains?: string
}): Promise<BacktestFixtureListResponse> {
  const q = new URLSearchParams()
  q.set('competition_id', String(params.competition_id))
  if (params.season_year != null) q.set('season_year', String(params.season_year))
  if (params.status) q.set('status', params.status)
  if (params.limit != null) q.set('limit', String(params.limit))
  if (params.offset != null) q.set('offset', String(params.offset))
  if (params.round_contains) q.set('round_contains', params.round_contains)
  return requestJson<BacktestFixtureListResponse>(`/api/backtest/debug/fixtures?${q.toString()}`)
}

export async function getBacktestPointInTimeContext(params: {
  competition_id: number
  fixture_id: number
  market_key?: string
  mode?: string
}): Promise<PointInTimeContextResponse> {
  const q = new URLSearchParams()
  q.set('competition_id', String(params.competition_id))
  q.set('fixture_id', String(params.fixture_id))
  if (params.market_key) q.set('market_key', params.market_key)
  if (params.mode) q.set('mode', params.mode)
  return requestJson<PointInTimeContextResponse>(
    `/api/backtest/debug/point-in-time-context?${q.toString()}`,
  )
}

// --- Backtest Engine Step E (SOT v2.1 PIT preview) ---

export type SotV21PreviewResponse = {
  status: string
  market_key: string
  algorithm_version: string
  mode: string
  competition_id: number
  fixture_id: number
  fixture: {
    home_team: string
    away_team: string
    kickoff_at: string
    round?: string | null
  }
  leakage_guard: boolean
  cutoff_time: string
  latest_fixture_used_at?: string | null
  actuals_used_as_input: boolean
  prediction: {
    home_predicted_sot?: number | null
    away_predicted_sot?: number | null
    total_predicted_sot?: number | null
  }
  actuals_for_scoring: {
    actual_home_sot?: number | null
    actual_away_sot?: number | null
    actual_total_sot?: number | null
    final_score?: string | null
    fixture_status?: string | null
  }
  errors: {
    home_error?: number | null
    away_error?: number | null
    total_error?: number | null
    home_abs_error?: number | null
    away_abs_error?: number | null
    total_abs_error?: number | null
  }
  home_trace: {
    base_anchor_sot: Record<string, unknown>
    weighted_macro_multiplier: number
    expected_sot_v21_pit?: number | null
    macros: {
      key: string
      label: string
      macro_weight: number
      macro_index: number
      status: string
      warnings: string[]
      components?: Record<string, unknown> | null
      source_paths?: string[] | null
    }[]
  }
  away_trace: SotV21PreviewResponse['home_trace']
  warnings: string[]
  fallback_variables: string[]
  feature_snapshot_json: Record<string, unknown>
}

export async function getBacktestSotV21Preview(params: {
  competition_id: number
  fixture_id: number
  mode?: string
}): Promise<SotV21PreviewResponse> {
  const q = new URLSearchParams()
  q.set('competition_id', String(params.competition_id))
  q.set('fixture_id', String(params.fixture_id))
  if (params.mode) q.set('mode', params.mode)
  return requestJson<SotV21PreviewResponse>(`/api/backtest/debug/sot-v21-preview?${q.toString()}`)
}

// --- Backtest Engine Step F (SOT v2.1 PIT mini-run) ---

export type SotV21MiniRunBucketStats = {
  fixtures_count: number
  total_mae?: number | null
  total_bias?: number | null
  avg_predicted_total_sot?: number | null
  avg_actual_total_sot?: number | null
}

export type SotV21MiniRunFixtureResult = {
  fixture_id: number
  round?: string | null
  kickoff_at: string
  home_team: string
  away_team: string
  predicted_home_sot?: number | null
  predicted_away_sot?: number | null
  predicted_total_sot?: number | null
  actual_home_sot?: number | null
  actual_away_sot?: number | null
  actual_total_sot?: number | null
  home_error?: number | null
  away_error?: number | null
  total_error?: number | null
  total_abs_error?: number | null
  leakage_guard: boolean
  actuals_used_as_input: boolean
  latest_fixture_used_at?: string | null
  cutoff_time: string
  home_prior_matches_count: number
  away_prior_matches_count: number
  warnings: string[]
  home_trace?: SotV21PreviewResponse['home_trace'] | null
  away_trace?: SotV21PreviewResponse['away_trace'] | null
}

export type SotV21MiniRunCaseBrief = {
  fixture_id: number
  kickoff_at: string
  round?: string | null
  home_team: string
  away_team: string
  predicted_home_sot?: number | null
  predicted_away_sot?: number | null
  predicted_total_sot?: number | null
  actual_home_sot?: number | null
  actual_away_sot?: number | null
  actual_total_sot?: number | null
  total_error?: number | null
  total_abs_error?: number | null
  home_prior_matches_count: number
  away_prior_matches_count: number
  warnings_count: number
}

export type SotV21MiniRunResponse = {
  status: string
  preview_only: boolean
  market_key: string
  algorithm_version: string
  competition_id: number
  competition_name: string
  mode: string
  selection: {
    limit: number
    offset: number
    round_number?: number | null
    round_contains?: string | null
    round_filter_mode?: string
    fixture_ids?: number[] | null
    order_by: string
  }
  summary: {
    fixtures_requested: number
    fixtures_processed: number
    fixtures_failed: number
    total_mae?: number | null
    home_mae?: number | null
    away_mae?: number | null
    total_rmse?: number | null
    total_bias?: number | null
    home_bias?: number | null
    away_bias?: number | null
    avg_predicted_total_sot?: number | null
    avg_actual_total_sot?: number | null
    overestimated_count: number
    underestimated_count: number
    exact_or_near_count: number
    high_error_count: number
  }
  split_summary?: {
    available_count: number
    partial_count: number
    fallback_count: number
    avg_home_split_index?: number | null
    avg_away_split_index?: number | null
  }
  sample_breakdown: {
    early_low_sample: SotV21MiniRunBucketStats
    medium_sample: SotV21MiniRunBucketStats
    stable_sample: SotV21MiniRunBucketStats
  }
  actual_total_breakdown: {
    low_total: SotV21MiniRunBucketStats
    medium_total: SotV21MiniRunBucketStats
    high_total: SotV21MiniRunBucketStats
  }
  worst_cases: SotV21MiniRunCaseBrief[]
  best_cases: SotV21MiniRunCaseBrief[]
  results: SotV21MiniRunFixtureResult[]
  failed_fixtures: { fixture_id: number; error_code: string; message: string }[]
  db_writes: boolean
}

export type SotV21MiniRunRequest = {
  competition_id: number
  mode?: string
  limit?: number
  offset?: number
  round_number?: number | null
  round_contains?: string | null
  fixture_ids?: number[] | null
  include_trace?: boolean
}

export async function postBacktestSotV21MiniRun(
  body: SotV21MiniRunRequest,
): Promise<SotV21MiniRunResponse> {
  return requestPostJson<SotV21MiniRunResponse>('/api/backtest/debug/sot-v21-mini-run', body)
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
  label?: string
  predictions_total: number
  predictions_count?: number
  upcoming_predictions: number
  next_round_predictions_count?: number
  readiness?: string
  status?: string
  last_generated_at?: string | null
  avg_expected_sot: number | null
  min_expected_sot: number | null
  max_expected_sot: number | null
  generated_at: string | null
  is_available_for_upcoming: boolean
  engine_status?: string
  is_experimental?: boolean
  model_label?: string
  registry_status?: string
  manifest_error?: string | null
  degraded?: boolean
  xg_applied_count?: number
  xg_fallback_count?: number
  valid_predictions?: number
  incomplete_predictions?: number
  missing_required_data_count?: number
  missing_fields_summary?: Record<string, number>
}

export type ModelInputsAvailable = {
  team_stats?: boolean
  player_profiles?: boolean
  lineups?: boolean
  sportapi_mappings?: boolean
  v11_base_ready?: boolean
  upcoming_fixtures?: boolean
}

export type LineupCoverageSummary = {
  next_round_fixture_count?: number
  next_round_sportapi_lineups_count?: number
  next_round_coverage_pct?: number
  confirmed_lineups_count?: number
  probable_lineups_count?: number
}

export type V20OperatingContext = {
  global_model_version?: string
  global_model_label?: string
  competition_id?: number
  competition_name?: string
  operating_mode?: string
  lineups_ready?: boolean
  lineups_probable_only?: boolean
  confirmed_lineups_count?: number
  probable_lineups_count?: number
  next_round_lineup_coverage_pct?: number
  inputs_available?: ModelInputsAvailable
}

export type LegacyModelRow = {
  model_version: string
  legacy_hidden?: boolean
  label?: string
}

export type ModelStatusResponse = {
  status?: string
  season: number
  competition_id?: number
  competition_key?: string
  competition_name?: string
  /** @deprecated Usare selected_model_version / recommended_model_version */
  global_model_version?: string
  /** @deprecated Usare selected_model_label / recommended_model_label */
  global_model_label?: string
  selected_model_version?: string | null
  selected_model_label?: string | null
  recommended_model_label?: string | null
  operating_mode?: string
  inputs_available?: ModelInputsAvailable
  v20_operating_context?: V20OperatingContext
  lineups_ready?: boolean
  lineups_probable_only?: boolean
  confirmed_lineups_count?: number
  probable_lineups_count?: number
  next_round_lineup_coverage_pct?: number
  active_model_version: string | null
  recommended_model_version?: string | null
  stable_model_version?: string | null
  legacy_models?: LegacyModelRow[]
  upcoming_fixtures_total?: number
  available_model_versions: ModelStatusVersionRow[]
  available_models?: ModelStatusVersionRow[]
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

export type PreMatchReadiness = {
  sportapi_mapping?: string
  lineup_freshness?: string
  roster_sync?: string
  player_mapping?: string
  model_v20?: string
}

export type UpcomingActiveSidePrediction = {
  expected_sot: number
  model_version: string
  baseline_v01_expected_sot?: number | null
  difference_from_v01?: number | null
  baseline_v11_expected_sot?: number | null
  difference_from_v11?: number | null
  pre_match_readiness?: PreMatchReadiness
  breakdown: Record<string, unknown> | null
}

export type QuickPlayMarket = {
  market_id: string
  label: string
  predicted_value: number | null
  statistical_pick: string | null
  cautious_pick: string | null
  statistical_margin?: number | null
  cautious_margin?: number | null
  statistical_risk?: string | null
  confidence_label?: string | null
  cautious_same_as_statistical?: boolean
}

export type LineupStatusPayload = {
  label: string
  has_lineup?: boolean
  confirmed?: boolean | null
  fetched_at?: string | null
}

export type LineupRefreshImpactReason = {
  text: string
  player_name?: string | null
  previous_status?: string | null
  new_status?: string | null
  impact_type?: string | null
  affected_team?: string | null
  affected_prediction?: string | null
  estimated_sot_impact?: number | null
}

export type LineupRefreshImpactDelta = {
  direction_total?: string | null
  delta_total_sot?: number | null
  direction_home?: string | null
  delta_home_sot?: number | null
  direction_away?: string | null
  delta_away_sot?: number | null
  before_total_sot?: number | null
  after_total_sot?: number | null
  before_home_sot?: number | null
  after_home_sot?: number | null
  before_away_sot?: number | null
  after_away_sot?: number | null
  main_reason?: string | null
  severity?: string | null
  reasons?: LineupRefreshImpactReason[]
}

export type LineupRefreshImpactPayload = LineupRefreshImpactDelta & {
  has_comparison: boolean
  model_version?: string | null
  created_at?: string | null
}

export type SportApiFetchLineupsResponse = {
  status: string
  message?: string
  fixture_id?: number
  refresh_result?: Record<string, unknown>
  impact_delta?: LineupRefreshImpactDelta | null
  impact_id?: number | null
}

export type SportApiRoundRefreshResultRow = {
  fixture_id: number
  status: string
  error?: string | null
  mapping_ok?: boolean
  lineups_ok?: boolean
  match_name?: string | null
  before_total_sot?: number | null
  after_total_sot?: number | null
  delta_total_sot?: number | null
  direction_total?: string | null
  main_reason?: string | null
}

export type SportApiRoundRefreshSummary = {
  status: string
  message?: string
  season?: number
  total_fixtures: number
  updated: number
  skipped_no_mapping: number
  skipped_recent: number
  failed: number
  v20_regenerated?: number
  up_count?: number
  down_count?: number
  flat_count?: number
  estimated_api_calls: number
  results?: SportApiRoundRefreshResultRow[]
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
  markets?: QuickPlayMarket[]
  lineup_status?: LineupStatusPayload | null
  lineup_refresh_impact?: LineupRefreshImpactPayload | null
  tracked_pick_badge?: string | null
  tracked_pick_summary?: string | null
  tracked_pick_badges?: string[]
  pre_match_job_updated_at?: string | null
  betting_advice_compact?: {
    total_expected_sot: number | null
    statistical_pick: string | null
    cautious_pick: string | null
    statistical_margin?: number | null
    cautious_margin?: number | null
    statistical_risk?: string | null
    confidence_label?: string | null
    cautious_same_as_statistical?: boolean
    model_label?: string | null
  } | null
  referee_summary?: RefereeSummary | null
}

export type RefereeSummary = {
  available: boolean
  referee_name?: string
  profile_available?: boolean
  avg_yellow_cards?: number | null
  avg_red_cards?: number | null
  severity_label?: string | null
  sample_quality?: string | null
  matches_count?: number
  message?: string
  season_profile?: {
    label?: string
    matches_count?: number
    avg_yellow_cards?: number | null
    avg_red_cards?: number | null
    severity_label?: string | null
    sample_quality?: string | null
    data_source?: string
    coverage_note?: string
  }
  home_team_context?: RefereeContextBlock
  away_team_context?: RefereeContextBlock
  direct_h2h_context?: RefereeContextBlock
}

export type UpcomingActiveResponse = {
  status?: string
  message?: string
  model_version?: string
  season: number
  competition_id?: number
  competition_name?: string
  model_version_used: string
  recommended_model_version: string
  stable_model_version?: string | null
  round: string | null
  matches_count: number
  matches: UpcomingActiveMatchRow[]
  model_limitations: ModelLimitations
  warnings: string[]
  info?: string[]
  lineup_coverage?: LineupCoverageSummary
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

/** Report rapido Prossima giornata (payload leggero, solo DB). */
export async function getNextRoundQuickReport(
  season: number,
  opts?: { limit?: number; onlyNextRound?: boolean; modelVersion?: string | null },
): Promise<UpcomingActiveResponse> {
  const p = new URLSearchParams()
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  if (opts?.onlyNextRound != null) p.set('only_next_round', String(opts.onlyNextRound))
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/next-round/quick-report${q ? `?${q}` : ''}`
  return requestJson<UpcomingActiveResponse>(path)
}

export type UpcomingFixtureDetailResponse = {
  status: string
  season: number
  competition_id?: number
  competition_name?: string
  code?: string
  step?: string
  message?: string
  fixture_id?: number
  match?: UpcomingActiveMatchRow
  model_limitations?: ModelLimitations
  referee_summary?: unknown
}

export async function getUpcomingFixtureDetailForCompetition(
  competitionId: number,
  fixtureId: number,
  opts?: { modelVersion?: string | null },
): Promise<UpcomingFixtureDetailResponse> {
  const p = new URLSearchParams()
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  const path = `/api/competitions/${competitionId}/predictions/sot/upcoming-fixture/${fixtureId}/detail${q ? `?${q}` : ''}`
  return requestJson<UpcomingFixtureDetailResponse>(path)
}

export type CompetitionAuditFixtureRow = {
  fixture_id: number
  api_fixture_id?: number
  match_name?: string
  kickoff?: string | null
  kickoff_at?: string | null
  round?: string | null
  status?: string | null
  status_short?: string | null
  has_prediction?: boolean
  competition_id?: number
  home_team: { id: number; name: string; logo_url?: string | null }
  away_team: { id: number; name: string; logo_url?: string | null }
}

export type CompetitionAuditFixturesResponse = {
  status?: string
  code?: string
  message?: string
  step?: string
  competition_id: number
  competition_name?: string
  season?: number
  scope?: string
  fixtures: CompetitionAuditFixtureRow[]
}

export function buildMatchAuditUrl(opts: {
  competitionId: number
  fixtureId: number
  modelVersion?: string | null
}): string {
  const p = new URLSearchParams()
  p.set('competition_id', String(opts.competitionId))
  p.set('fixture_id', String(opts.fixtureId))
  if (opts.modelVersion) p.set('model_version', opts.modelVersion)
  return `/match-variable-audit?${p.toString()}`
}

export async function getCompetitionAuditFixtures(
  competitionId: number,
  opts?: {
    scope?: 'next_round' | 'upcoming' | 'all_with_predictions'
    modelVersion?: string | null
    limit?: number
  },
): Promise<CompetitionAuditFixturesResponse> {
  const p = new URLSearchParams()
  if (opts?.scope) p.set('scope', opts.scope)
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  if (opts?.limit != null) p.set('limit', String(opts.limit))
  const q = p.toString()
  return requestJson<CompetitionAuditFixturesResponse>(
    `/api/competitions/${competitionId}/predictions/sot/fixtures${q ? `?${q}` : ''}`,
  )
}

export async function getCompetitionFixtureExplanation(
  competitionId: number,
  fixtureId: number,
  opts?: { modelVersion?: string | null },
): Promise<SotFixtureExplanationResponse & { competition_id?: number; competition_name?: string }> {
  const p = new URLSearchParams()
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  return requestJson(
    `/api/competitions/${competitionId}/predictions/sot/fixture/${fixtureId}/explanation${q ? `?${q}` : ''}`,
  )
}

export type LineupPlayerMappingDebugResponse = {
  status: string
  competition_id?: number | null
  fixture_id: number
  home_team?: string
  away_team?: string
  lineup_players_count?: number
  player_profiles_count?: number
  profiles_available_home?: number
  profiles_available_away?: number
  matched_players?: number
  unmatched_players?: number
  mapping_rate?: number
  lineup_mapping_stats?: {
    starters_total?: number
    starters_matched_auto_safe?: number
    starters_matched_any?: number
    mapping_rate?: number
  }
  rows?: import('../types/lineupImpact').LineupPlayerMappingDebugRow[]
}

export async function getLineupPlayerMappingDebug(
  competitionId: number,
  fixtureId: number,
): Promise<LineupPlayerMappingDebugResponse> {
  return requestJson(
    `/api/competitions/${competitionId}/fixtures/${fixtureId}/lineup-player-mapping-debug`,
  )
}

export async function getUpcomingFixtureDetail(
  season: number,
  fixtureId: number,
  opts?: { modelVersion?: string | null },
): Promise<UpcomingFixtureDetailResponse> {
  const p = new URLSearchParams()
  if (opts?.modelVersion) p.set('model_version', opts.modelVersion)
  const q = p.toString()
  const path = `/api/predictions/sot/serie-a/${season}/upcoming-fixture/${fixtureId}/detail${q ? `?${q}` : ''}`
  return requestJson<UpcomingFixtureDetailResponse>(path)
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

export type PlayerProfilesLimit = 5 | 10 | 15 | 25 | 'all'

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

export async function fetchSportApiLineups(
  fixtureId: number,
  opts?: AdminRequestOpts & { trackImpact?: boolean; regenerateV20?: boolean },
): Promise<SportApiFetchLineupsResponse> {
  const p = new URLSearchParams()
  if (opts?.trackImpact) p.set('track_impact', 'true')
  if (opts?.regenerateV20 === false) p.set('regenerate_v20', 'false')
  else if (opts?.trackImpact || opts?.regenerateV20) p.set('regenerate_v20', 'true')
  const q = p.toString()
  return adminPostJson<SportApiFetchLineupsResponse>(
    `/api/admin/sportapi/lineups/${fixtureId}/fetch${q ? `?${q}` : ''}`,
    {},
    {
      ...opts,
      timeoutMs: opts?.timeoutMs ?? 120_000,
    },
  )
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

export type SportApiPlayerMatchingPreviewResponse = {
  fixture_id: number
  sportapi_lineups_available?: boolean
  player_matching?: unknown
  lineup_impact_simulation?: import('../types/lineupImpact').LineupImpactSimulationPayload
}

export async function getSportApiPlayerMatchingPreview(
  fixtureId: number,
  opts?: AdminRequestOpts,
): Promise<SportApiPlayerMatchingPreviewResponse> {
  return adminGetJson<SportApiPlayerMatchingPreviewResponse>(
    `/api/admin/sportapi/fixture/${fixtureId}/player-matching`,
    opts,
  )
}

export async function syncSportApiFixtureSquads(
  fixtureId: number,
  opts?: AdminRequestOpts,
): Promise<unknown> {
  return adminPostJson<unknown>(
    `/api/admin/sportapi/fixture/${fixtureId}/sync-api-squads`,
    {},
    opts,
  )
}

export async function buildPlayerSotProfiles(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/features/player-sot-profiles/serie-a/${season}/build`, {}, opts)
}

export async function getPlayerSotProfilesSummary(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminGetJson<unknown>(`/api/features/player-sot-profiles/serie-a/${season}/summary`, opts)
}
