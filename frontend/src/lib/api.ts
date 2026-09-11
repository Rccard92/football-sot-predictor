/** Client HTTP verso il backend. Base URL da `VITE_API_BASE_URL` (senza trailing slash). */

import type { SportApiFixtureDebugResponse, SportApiLineupsStoredResponse } from '../types/sportapi'
import type { FixturePlayerProfilesResponse } from '../types/playerDbProfiles'

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

export type IngestionRunsResponse = {
  runs: IngestionRunSummary[]
  total: number
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
    // Formati standard backend
    if (typeof o.error_message === 'string') return o.error_message
    if (typeof o.error_code === 'string' && typeof o.error_message === 'string') {
      return `${o.error_code}: ${o.error_message}`
    }
    if (typeof o.error_code === 'string') return String(o.error_code)
    if (typeof o.message === 'string') return o.message
    if (typeof o.detail === 'string') return o.detail
    if (o.detail && typeof o.detail === 'object') {
      const d = o.detail as Record<string, unknown>
      if (typeof d.error_message === 'string' && typeof d.error_code === 'string') {
        return `${d.error_code}: ${d.error_message}`
      }
      if (typeof d.error_message === 'string') return d.error_message
      if (typeof d.message === 'string' && typeof d.code === 'string') return `${d.code}: ${d.message}`
      if (typeof d.message === 'string') return d.message
      if (typeof d.code === 'string') return d.code
    }
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

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, init)

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

export type ApiFootballFixtureMarketValue = {
  raw_value: string
  odd: number | null
  normalized_selection?: string
}

export type ApiFootballFixtureMarketRow = {
  provider_market_id: string
  raw_market_name: string
  normalized_market: string
  values: ApiFootballFixtureMarketValue[]
}

export type ApiFootballFixtureBookmakerMarkets = {
  bookmaker_id: number
  bookmaker_name: string
  markets: ApiFootballFixtureMarketRow[]
  error?: string
}

export type ApiFootballOverCandidate = {
  bookmaker_id: number
  bookmaker_name: string
  raw_market_name: string
  provider_market_id?: string
  raw_value: string
  normalized_selection?: string
  odd: number | null
}

export type ApiFootballFixtureMarketsDebugResponse = {
  status: string
  provider_source: string
  provider_fixture_id: number
  fixture_id?: number | null
  bookmakers: ApiFootballFixtureBookmakerMarkets[]
  detected_over_candidates?: ApiFootballOverCandidate[]
  errors?: string[]
  message?: string
}

export async function getApiFootballFixtureMarketsDebug(params: {
  fixture_id?: number
  provider_fixture_id?: number
  provider_source?: string
  bookmaker_ids?: string
}): Promise<ApiFootballFixtureMarketsDebugResponse> {
  const q = new URLSearchParams()
  if (params.fixture_id != null) q.set('fixture_id', String(params.fixture_id))
  if (params.provider_fixture_id != null) q.set('provider_fixture_id', String(params.provider_fixture_id))
  if (params.provider_source) q.set('provider_source', params.provider_source)
  if (params.bookmaker_ids) q.set('bookmaker_ids', params.bookmaker_ids)
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return adminGetJson<ApiFootballFixtureMarketsDebugResponse>(
    `/api/admin/bookmakers/fixture-markets-debug${suffix}`,
  )
}

export type BookmakerRawOddsValue = {
  raw_value: string
  normalized_selection: string
  odd: number | string | null
}

export type BookmakerRawOddsMarket = {
  bet_id: string
  raw_market_name: string
  normalized_market: string
  values: BookmakerRawOddsValue[]
}

export type BookmakerRawOddsBookmaker = {
  bookmaker_id: number
  bookmaker_name: string
  markets: BookmakerRawOddsMarket[]
  raw_payload?: { bets: unknown[] }
  error?: string
}

export type BookmakerOverUnderDebugEntry = {
  found: boolean
  found_in_bookmakers: string[]
  raw_market_name: string | null
  bet_id: string | null
  raw_values: string[]
}

export type BookmakerOverUnderRejectedEntry = {
  bookmaker_name: string
  raw_market_name: string
  bet_id: string | null
  raw_value: string
  selection_key: string
  reason: string
}

export type BookmakerOverUnderFullTimeDebug = {
  OVER_1_5: BookmakerOverUnderDebugEntry
  OVER_2_5: BookmakerOverUnderDebugEntry
  rejected_from_markets: BookmakerOverUnderRejectedEntry[]
}

export type BookmakerOverUnderFirstHalfDebug = {
  OVER_PT_0_5: BookmakerOverUnderDebugEntry
  OVER_PT_1_5: BookmakerOverUnderDebugEntry
  rejected_from_markets: BookmakerOverUnderRejectedEntry[]
}

export type BookmakerFixtureRawOddsResponse = {
  status: string
  provider_source: string
  provider_fixture_id: number
  bookmakers_requested: Array<{ id: number; name: string }>
  bookmakers: BookmakerRawOddsBookmaker[]
  summary: {
    bookmakers_found: string[]
    markets_found: string[]
    over_under_candidates: string[]
    match_winner_found: boolean
    over_1_5_found: boolean
    over_2_5_found: boolean
    over_pt_0_5_found: boolean
    over_pt_1_5_found: boolean
    draw_pt_found: boolean
  }
  over_under_full_time_debug: BookmakerOverUnderFullTimeDebug
  over_under_first_half_debug: BookmakerOverUnderFirstHalfDebug
  message?: string
}

export async function getBookmakerFixtureRawOdds(params: {
  provider_fixture_id: number
  provider_source?: string
  bookmaker_ids?: string
  include_raw?: boolean
}): Promise<BookmakerFixtureRawOddsResponse> {
  const q = new URLSearchParams()
  q.set('provider_fixture_id', String(params.provider_fixture_id))
  if (params.provider_source) q.set('provider_source', params.provider_source)
  if (params.bookmaker_ids) q.set('bookmaker_ids', params.bookmaker_ids)
  if (params.include_raw != null) q.set('include_raw', String(params.include_raw))
  return adminGetJson<BookmakerFixtureRawOddsResponse>(
    `/api/admin/bookmakers/fixture-raw-odds?${q.toString()}`,
  )
}

export type BookmakerProviderSourceRow = {
  provider_source: string
  label: string
  status: 'available' | 'not_configured' | 'error'
  bookmakers_count: number
  last_synced_at: string | null
  supports_fixture_odds?: boolean
  note?: string | null
}

export type BookmakerProvidersDiscoveryResponse = {
  sources: BookmakerProviderSourceRow[]
  checked_at: string
}

export type UnifiedBookmakerRow = {
  provider_source: string
  provider_bookmaker_id: string
  provider_slug?: string
  name: string
  is_selected: boolean
  last_synced_at: string | null
  working_odds_provider_id?: number | null
}

export type BookmakerMarketsDiscoveryResponse = {
  markets: Array<{
    id: number | null
    provider_source: string
    provider_market_id: string
    market_key: string
    market_name: string
    normalized_market: string
    is_unknown: boolean
  }>
  total: number
}

export type BookmakerCoverageResponse = {
  competition_id: number
  competition_key: string
  round_label: string | null
  market: string
  provider_source: string | null
  fixtures_total: number
  fixtures_with_odds: number
  coverage_pct: number
  bookmakers_found: string[]
  fixtures: Array<{
    fixture_id: number
    kickoff_at: string | null
    home_team: string | null
    away_team: string | null
    has_odds: boolean
    odds_count: number
    sample_odds: Array<{
      bookmaker_name: string
      provider_source: string
      home_odds: number | null
      draw_odds: number | null
      away_odds: number | null
    }>
  }>
}

export type BookmakerSyncNextRoundResponse = {
  status: string
  competition_id: number
  round_label: string | null
  market: string
  provider_source: string
  fixtures_checked: number
  odds_saved: number
  bookmakers_found: string[]
  markets_found: string[]
  failed: string[]
  warnings: string[]
  message?: string
}

export async function getBookmakerDiscoveryProviders(): Promise<BookmakerProvidersDiscoveryResponse> {
  return adminGetJson<BookmakerProvidersDiscoveryResponse>('/api/admin/bookmakers/providers')
}

export async function getUnifiedBookmakersList(): Promise<{ bookmakers: UnifiedBookmakerRow[]; total: number }> {
  return adminGetJson('/api/admin/bookmakers/providers/bookmakers')
}

export async function getBookmakerDiscoveryMarkets(
  providerSource?: string,
): Promise<BookmakerMarketsDiscoveryResponse> {
  const q = providerSource ? `?provider_source=${encodeURIComponent(providerSource)}` : ''
  return adminGetJson<BookmakerMarketsDiscoveryResponse>(`/api/admin/bookmakers/markets${q}`)
}

export async function getCompetitionBookmakerCoverage(
  competitionId: number,
  params?: { only_next_round?: boolean; market?: string; provider_source?: string },
): Promise<BookmakerCoverageResponse> {
  const sp = new URLSearchParams()
  if (params?.only_next_round !== undefined) sp.set('only_next_round', String(params.only_next_round))
  if (params?.market) sp.set('market', params.market)
  if (params?.provider_source) sp.set('provider_source', params.provider_source)
  const qs = sp.toString() ? `?${sp}` : ''
  return adminGetJson<BookmakerCoverageResponse>(
    `/api/admin/competitions/${competitionId}/bookmakers/coverage${qs}`,
  )
}

export async function postCompetitionSyncNextRoundOdds(
  competitionId: number,
  body?: { market?: string; provider_source?: string; bookmaker_name?: string; provider_slug?: string },
  opts?: AdminRequestOpts,
): Promise<BookmakerSyncNextRoundResponse> {
  return adminPostJson<BookmakerSyncNextRoundResponse>(
    `/api/admin/competitions/${competitionId}/bookmakers/sync-next-round-odds`,
    body ?? {},
    opts,
  )
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

export type RoundAnalysisModelBlock = {
  model_version?: string
  model_version_requested?: string
  model_version_used?: string
  model_engine_name?: string
  model_status?: 'ok' | 'no_prediction' | 'error' | string
  status?: 'ok' | 'no_prediction' | 'error' | string
  error_code?: string | null
  error_message?: string | null
  reason?: string | null
  message?: string | null
  label?: string
  trace_summary?: Record<string, unknown> | null
  predicted_home_sot?: number | null
  predicted_away_sot?: number | null
  predicted_total_sot?: number | null
  aggressive_line?: number | null
  aggressive_edge?: number | null
  aggressive_outcome?: string | null
  aggressive_advice?: string | null
  aggressive_reason?: string | null
  cautious_line?: number | null
  cautious_edge?: number | null
  cautious_outcome?: string | null
  cautious_advice?: string | null
  cautious_reason?: string | null
  confidence?: string | null
  sample_bucket?: string | null
  warnings?: string[]
  data_quality?: Record<string, string>
  human_explanation?: {
    headline?: string
    summary?: string
    decision_reason?: string
    risk_reason?: string
    line_reason?: string
    confidence_reason?: string
    key_factors?: string[]
    warning_notes?: string[]
    italian_text?: string
    short_reason?: string
    data_used?: Record<string, number | string | null | undefined>
  }
  v1_1_predicted_total?: number | null
  v2_1_predicted_total?: number | null
  prediction_gap?: number | null
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

export async function adminIngestStandings(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/standings`, {}, opts)
}

export async function adminIngestTeamStats(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminPostJson<unknown>(`/api/admin/ingest/serie-a/${season}/team-stats`, {}, opts)
}

export async function getPlayerMatchDbSummary(season: number, opts?: AdminRequestOpts): Promise<unknown> {
  return adminGetJson<unknown>(`/api/admin/debug/serie-a/${season}/player-db-summary`, opts)
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
