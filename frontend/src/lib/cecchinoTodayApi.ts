/**
 * Client API Cecchino Today — discovery giornaliera (separato da SOT e Cecchino classico).
 */

import { adminPostJson, requestJson } from './api'

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
  message?: string
  cleanup?: { deleted: number; cutoff_date: string }
}

export type CecchinoTodayDay = {
  date: string
  label: string
  eligible_count: number
  excluded_count: number
  last_scan_at: string | null
  status: 'available' | 'pending'
}

export type CecchinoTodayDaysResponse = {
  status: string
  version: string
  timezone: string
  today: string
  tomorrow: string
  days: CecchinoTodayDay[]
}

export type CecchinoTodayScanMeta = {
  has_scan: boolean
  eligible_count: number
  excluded_count: number
  last_scan_at: string | null
  day_status: 'available' | 'pending'
}

export type CecchinoTodayListFixture = {
  id: number
  provider_fixture_id: number
  local_fixture_id: number | null
  competition_id: number | null
  home_team_name: string | null
  away_team_name: string | null
  kickoff: string | null
  bookmaker_status: string | null
  stats_status: string | null
  cecchino_status: string | null
  bookmakers: Record<string, string>
}

export type CecchinoTodayListResponse = {
  status: string
  version: string
  scan_date: string
  total: number
  countries: Array<{
    country_name: string
    leagues: Array<{
      league_name: string
      fixtures: CecchinoTodayListFixture[]
    }>
  }>
  scan_meta?: CecchinoTodayScanMeta
}

export type CecchinoTodayDetailResponse = {
  status: string
  version?: string
  id?: number
  scan_date?: string
  provider_fixture_id?: number
  local_fixture_id?: number | null
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
  bookmaker_debug: Record<string, string>
  stats_debug: Record<string, unknown>
  competition_filter_debug: Record<string, unknown>
  warnings: string[]
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

export function tomorrowIsoRome(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Rome' }).format(d)
}

export async function scanCecchinoToday(body: {
  scan_date?: string
  timezone?: string
} = {}): Promise<CecchinoTodayScanReport> {
  return adminPostJson<CecchinoTodayScanReport>('/api/admin/cecchino/today/scan', body)
}

export async function scanCecchinoTodayToday(): Promise<CecchinoTodayScanReport> {
  return adminPostJson<CecchinoTodayScanReport>('/api/admin/cecchino/today/scan-today', {})
}

export async function scanCecchinoTodayTomorrow(): Promise<CecchinoTodayScanReport> {
  return adminPostJson<CecchinoTodayScanReport>('/api/admin/cecchino/today/scan-tomorrow', {})
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

export async function cleanupCecchinoToday(retentionDays = 7): Promise<{
  status: string
  deleted: number
  cutoff_date: string
}> {
  return adminPostJson('/api/admin/cecchino/today/cleanup', {
    retention_days: retentionDays,
    timezone: 'Europe/Rome',
  })
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
