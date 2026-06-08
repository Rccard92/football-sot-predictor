import { adminGetJson, adminPostJson } from './api'

export type SignalsBucket = {
  activations: number
  settled: number
  won: number
  lost: number
  pending: number
  not_evaluable: number
  success_rate: number | null
  eligible_fixtures_count?: number
  fixtures_with_signals_count?: number
  avg_signals_per_fixture?: number | null
}

export type SignalsDiagnostics = {
  date_from: string
  date_to: string
  today_fixtures_count: number
  eligible_fixtures_count: number
  fixtures_with_signal_matrix_count: number
  signal_activations_count: number
  current_signal_activations_count: number
  evaluated_count: number
  won: number
  lost: number
  pending: number
  not_evaluable: number
  date_filter_field_used: string
  warnings: string[]
}

export type SignalsSummaryResponse = {
  filters: Record<string, unknown>
  overall: SignalsBucket
  by_signal: Array<SignalsBucket & { signal_group: string; signal_label: string }>
  by_column: Array<SignalsBucket & { source_column: string }>
  by_signal_and_column: Array<
    SignalsBucket & { signal_group: string; signal_label: string; source_column: string }
  >
  diagnostics?: SignalsDiagnostics
}

export type SignalsBackfillResponse = {
  status: string
  fixtures_found: number
  fixtures_with_signals: number
  fixtures_skipped: number
  signals_created: number
  signals_updated: number
  signals_deactivated: number
  evaluated: number
  won: number
  lost: number
  pending: number
  not_evaluable: number
  remapped?: number
  legacy_scala_deactivated?: number
  force_remap?: boolean
  warnings: string[]
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
  include_diagnostics?: boolean
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
      include_diagnostics: filters.include_diagnostics ?? false,
    })}`,
  )
}

export async function getCecchinoSignalsDiagnostics(params: {
  date_from: string
  date_to: string
}): Promise<SignalsDiagnostics> {
  return adminGetJson<SignalsDiagnostics>(
    `/api/admin/cecchino/signals/diagnostics${qs({
      date_from: params.date_from,
      date_to: params.date_to,
    })}`,
  )
}

export async function backfillCecchinoSignals(params: {
  date_from: string
  date_to: string
  only_missing?: boolean
  evaluate_after?: boolean
  force_remap?: boolean
}): Promise<SignalsBackfillResponse> {
  return adminPostJson<SignalsBackfillResponse>('/api/admin/cecchino/signals/backfill', {
    date_from: params.date_from,
    date_to: params.date_to,
    only_missing: params.only_missing ?? true,
    evaluate_after: params.evaluate_after ?? true,
    force_remap: params.force_remap ?? false,
  })
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
  sync_missing?: boolean
  force_remap?: boolean
}): Promise<{
  status: string
  fixtures: number
  evaluated: number
  pending: number
  not_evaluable: number
  force_remap?: boolean
  backfill_summary?: SignalsBackfillResponse
}> {
  return adminPostJson('/api/admin/cecchino/signals/revaluate', {
    date_from: params.date_from,
    date_to: params.date_to,
    force: params.force ?? false,
    sync_missing: params.sync_missing ?? false,
    force_remap: params.force_remap ?? false,
  })
}

export const SIGNAL_GROUPS = [
  { value: '', label: 'Tutti' },
  { value: 'UNDER_UNDER_PT', label: 'UNDER 2.5' },
  { value: 'DRAW', label: 'SEGNO X' },
  { value: 'OVER_OVER_PT', label: 'OVER 2.5' },
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
  { group: 'UNDER_UNDER_PT', label: 'UNDER 2.5' },
  { group: 'DRAW', label: 'SEGNO X' },
  { group: 'OVER_OVER_PT', label: 'OVER 2.5' },
  { group: 'HOME', label: '1' },
  { group: 'ONE_X', label: '1X' },
  { group: 'AWAY', label: '2' },
  { group: 'X_TWO', label: 'X2' },
  { group: 'ONE_TWO', label: '12' },
] as const

export const HEATMAP_COLUMNS = ['EXCEL_D', 'EXCEL_E', 'EXCEL_F', 'EXCEL_G', 'SCALA'] as const
