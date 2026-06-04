/**
 * Client API Cecchino Today — discovery giornaliera (separato da SOT e Cecchino classico).
 */

import { adminPostJson, requestJson } from './api'

export type CecchinoTodayScanReport = {
  status: string
  version: string
  scan_date: string
  total_discovered: number
  eligible: number
  excluded: Record<string, number>
  excluded_total?: number
  fixtures_processed?: number
  warnings: string[]
  message?: string
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

export type CecchinoTodayExcludedResponse = {
  status: string
  version: string
  scan_date: string
  total: number
  fixtures: Array<{
    id: number
    provider_fixture_id: number
    home_team_name: string | null
    away_team_name: string | null
    league_name: string | null
    country_name: string | null
    kickoff: string | null
    eligibility_status: string
    eligibility_reason: string | null
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

export async function scanCecchinoToday(body: {
  scan_date?: string
  timezone?: string
} = {}): Promise<CecchinoTodayScanReport> {
  return adminPostJson<CecchinoTodayScanReport>('/api/admin/cecchino/today/scan', body)
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
      timezone: params.timezone,
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
    `/api/admin/cecchino/today/excluded${qs({ date: params.date, timezone: params.timezone })}`,
  )
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
