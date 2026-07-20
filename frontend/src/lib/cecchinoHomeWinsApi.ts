/**
 * Client API Monitoraggio Segno 1 — coorte vittorie casalinghe (esito reale 1).
 */

import { AdminHttpError, adminGetJson } from './api'

const BASE = '/api/cecchino/home-wins'

export type HomeWinsCompleteness = 'complete' | 'partial' | ''

export type HomeWinsFilters = {
  date_from?: string
  date_to?: string
  competition_id?: number
  country?: string
  league?: string
  team?: string
  completeness?: HomeWinsCompleteness
  page?: number
  page_size?: number
}

export type HomeWinsListItem = {
  today_fixture_id: number
  provider_fixture_id: number | null
  local_fixture_id: number | null
  competition_id: number | null
  scan_date: string | null
  kickoff: string | null
  country: string | null
  league: string | null
  home_team: string | null
  away_team: string | null
  ft_home: number
  ft_away: number
  ht_home: number | null
  ht_away: number | null
  goal_difference: number
  total_goals: number
  outcome_1x2: '1'
  result_source: string
  eligibility_status: string
  kpi_availability: string
  balance_availability: string
  goal_intensity_availability: string
  completeness_status: 'complete' | 'partial'
  has_kpi: boolean
  has_balance: boolean
  has_goal_intensity_v5: boolean
}

export type HomeWinsSummary = {
  total_home_wins: number
  complete: number
  partial: number
  competitions_count: number
  scan_date_min: string | null
  scan_date_max: string | null
  pct_with_kpi: number
  pct_with_balance: number
  pct_with_goal_intensity_v5: number
}

export type HomeWinsListResponse = {
  status: string
  dataset_version: string
  selection_contract: {
    cohort: string
    outcome: string
    signal_1_used_for_selection: boolean
  }
  total: number
  page: number
  page_size: number
  summary: HomeWinsSummary
  available_filters: {
    countries?: string[]
    leagues?: string[]
    competitions?: Array<{
      competition_id: number
      league: string
      country: string
    }>
    completeness?: string[]
  }
  items: HomeWinsListItem[]
}

export type HomeWinsDetailResponse = {
  status: string
  dataset_version?: string
  selection_contract?: Record<string, unknown>
  identity?: Record<string, unknown>
  post_match_outcome?: Record<string, unknown>
  source_integrity?: Record<string, unknown>
  pre_match_snapshot?: {
    kpi_panel?: Record<string, unknown>
    cecchino_output?: Record<string, unknown>
    balance_v5_monitoring?: Record<string, unknown>
    goal_intensity_v5_preview?: Record<string, unknown>
    purchasability_preview?: Record<string, unknown>
    odds_snapshot?: Record<string, unknown>
    stats_snapshot?: Record<string, unknown>
    xg_profiles?: Record<string, unknown>
  }
  observational?: Record<string, unknown>
  warnings?: string[]
  reason?: string
}

function qs(filters: HomeWinsFilters): string {
  const p = new URLSearchParams()
  if (filters.date_from) p.set('date_from', filters.date_from)
  if (filters.date_to) p.set('date_to', filters.date_to)
  if (filters.competition_id != null) p.set('competition_id', String(filters.competition_id))
  if (filters.country) p.set('country', filters.country)
  if (filters.league) p.set('league', filters.league)
  if (filters.team) p.set('team', filters.team)
  if (filters.completeness) p.set('completeness', filters.completeness)
  if (filters.page != null) p.set('page', String(filters.page))
  if (filters.page_size != null) p.set('page_size', String(filters.page_size))
  const s = p.toString()
  return s ? `?${s}` : ''
}

function apiBase(): string {
  return (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
}

export async function getHomeWinsList(
  filters: HomeWinsFilters = {},
): Promise<HomeWinsListResponse> {
  return adminGetJson(`${BASE}${qs(filters)}`)
}

export async function getHomeWinsDetail(
  todayFixtureId: number,
): Promise<HomeWinsDetailResponse> {
  return adminGetJson(`${BASE}/${todayFixtureId}`)
}

export async function downloadHomeWinsDataset(
  filters: Omit<HomeWinsFilters, 'page' | 'page_size'> = {},
): Promise<void> {
  const res = await fetch(`${apiBase()}${BASE}/export${qs(filters)}`)
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = body?.detail || body?.message || body?.reason || message
    } catch {
      /* ignore */
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(cd)
  const filename = match?.[1] || 'SOT_CECCHINO_HOME_WINS_DATASET.zip'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function availabilityBadgeLabel(status: string): string {
  if (status === 'available') return 'OK'
  return 'N/D'
}
