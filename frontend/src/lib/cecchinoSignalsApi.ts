import { adminGetJson, adminPostJson } from './api'

export type SignalsBucket = {
  activations: number
  settled: number
  won: number
  lost: number
  pending: number
  not_evaluable: number
  success_rate: number | null
}

export type SignalsSummaryResponse = {
  filters: Record<string, unknown>
  overall: SignalsBucket
  by_signal: Array<SignalsBucket & { signal_group: string; signal_label: string }>
  by_column: Array<SignalsBucket & { source_column: string }>
  by_signal_and_column: Array<
    SignalsBucket & { signal_group: string; signal_label: string; source_column: string }
  >
}

export type SignalActivationRow = {
  id: number
  today_fixture_id: number
  scan_date: string
  kickoff: string | null
  match: string
  country_name: string | null
  league_name: string | null
  signal_group: string
  signal_label: string
  source_column: string
  target_market_label: string | null
  evaluation_status: string
  evaluation_reason: string | null
  ft_score: string | null
  ht_score: string | null
  quota_book: number | null
  quota_cecchino: number | null
  edge_pct: number | null
  rating: number | null
  is_current: boolean
}

export type SignalsActivationsResponse = {
  items: SignalActivationRow[]
  total: number
  limit: number
  offset: number
}

export type SignalsFilters = {
  date_from: string
  date_to: string
  source_column?: string
  signal_group?: string
  league_name?: string
  country_name?: string
  evaluation_status?: string
  only_current?: boolean
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts: string[] = []
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

export async function getCecchinoSignalsSummary(
  filters: SignalsFilters,
): Promise<SignalsSummaryResponse> {
  return adminGetJson<SignalsSummaryResponse>(
    `/api/admin/cecchino/signals/summary${qs({
      date_from: filters.date_from,
      date_to: filters.date_to,
      source_column: filters.source_column,
      signal_group: filters.signal_group,
      league_name: filters.league_name,
      country_name: filters.country_name,
      evaluation_status: filters.evaluation_status,
      only_current: filters.only_current ?? true,
    })}`,
  )
}

export async function getCecchinoSignalsActivations(
  filters: SignalsFilters & { limit?: number; offset?: number },
): Promise<SignalsActivationsResponse> {
  return adminGetJson<SignalsActivationsResponse>(
    `/api/admin/cecchino/signals/activations${qs({
      date_from: filters.date_from,
      date_to: filters.date_to,
      source_column: filters.source_column,
      signal_group: filters.signal_group,
      league_name: filters.league_name,
      country_name: filters.country_name,
      evaluation_status: filters.evaluation_status,
      only_current: filters.only_current ?? true,
      limit: filters.limit ?? 100,
      offset: filters.offset ?? 0,
    })}`,
  )
}

export function buildCecchinoSignalsExportUrl(filters: SignalsFilters): string {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const prefix = String(base).replace(/\/$/, '')
  return `${prefix}/api/admin/cecchino/signals/export.csv${qs({
    date_from: filters.date_from,
    date_to: filters.date_to,
    source_column: filters.source_column,
    signal_group: filters.signal_group,
    league_name: filters.league_name,
    country_name: filters.country_name,
    evaluation_status: filters.evaluation_status,
    only_current: filters.only_current ?? true,
  })}`
}

export async function revaluateCecchinoSignals(params: {
  date_from: string
  date_to: string
  force?: boolean
}): Promise<{ status: string; fixtures: number; evaluated: number; pending: number; not_evaluable: number }> {
  return adminPostJson('/api/admin/cecchino/signals/revaluate', {
    date_from: params.date_from,
    date_to: params.date_to,
    force: params.force ?? false,
  })
}

export const SIGNAL_GROUPS = [
  { value: '', label: 'Tutti' },
  { value: 'UNDER_UNDER_PT', label: 'UNDER / UNDER PT' },
  { value: 'DRAW', label: 'SEGNO X' },
  { value: 'OVER_OVER_PT', label: 'OVER / OVER PT' },
  { value: 'HOME', label: '1' },
  { value: 'ONE_X', label: '1X' },
  { value: 'AWAY', label: '2' },
  { value: 'X_TWO', label: 'X2' },
  { value: 'ONE_TWO', label: '12' },
] as const

export const SOURCE_COLUMNS = [
  { value: '', label: 'Tutte' },
  { value: 'EXCEL_D', label: 'Excel D' },
  { value: 'EXCEL_E', label: 'Excel E' },
  { value: 'EXCEL_F', label: 'Excel F' },
  { value: 'EXCEL_G', label: 'Excel G' },
  { value: 'SCALA', label: 'Scala' },
] as const

export const EVAL_STATUSES = [
  { value: '', label: 'Tutti' },
  { value: 'pending', label: 'Pending' },
  { value: 'won', label: 'Vinti' },
  { value: 'lost', label: 'Persi' },
  { value: 'not_evaluable', label: 'Non valutabili' },
] as const

export const HEATMAP_SIGNAL_ROWS = [
  { group: 'UNDER_UNDER_PT', label: 'UNDER / UNDER PT' },
  { group: 'DRAW', label: 'SEGNO X' },
  { group: 'OVER_OVER_PT', label: 'OVER / OVER PT' },
  { group: 'HOME', label: '1' },
  { group: 'ONE_X', label: '1X' },
  { group: 'AWAY', label: '2' },
  { group: 'X_TWO', label: 'X2' },
  { group: 'ONE_TWO', label: '12' },
] as const

export const HEATMAP_COLUMNS = ['EXCEL_D', 'EXCEL_E', 'EXCEL_F', 'EXCEL_G', 'SCALA'] as const
