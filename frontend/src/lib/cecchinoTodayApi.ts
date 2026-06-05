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
  result_summary: Record<string, unknown> | null
  warnings: string[]
  errors: string[]
  started_at: string | null
  finished_at: string | null
  created_at?: string | null
  updated_at?: string | null
}

export const SCAN_JOB_POLL_MS = 2500

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

export type CecchinoTodayScore = {
  home: number | null
  away: number | null
  available: boolean
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
}

export type CecchinoBookmakerOddsDetailRow = {
  market_key: string
  label: string
  bookmakers: Record<string, number | null>
  book_average: number | null
  status: string
}

export type CecchinoBookmakerOddsDetail = {
  rows: CecchinoBookmakerOddsDetailRow[]
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
  kpi_panel?: import('./cecchinoApi').CecchinoKpiPanel
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
