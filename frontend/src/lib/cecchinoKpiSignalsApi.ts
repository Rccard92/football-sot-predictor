import { adminGetJson, adminPostJson } from './api'

export const KPI_RATING_BUCKETS = ['50-59', '60-69', '70-79', '80-89', '90-99', '100'] as const

export const KPI_HEATMAP_ROWS = [
  '1',
  'X',
  '2',
  '1X',
  'X2',
  '12',
  'Over 1.5',
  'Over 2.5',
  'Under 2.5',
  'Under 3.5',
  'Over PT 0.5',
  'Over PT 1.5',
  'Under PT 1.5',
] as const

export const KPI_EVAL_STATUSES = ['pending', 'won', 'lost', 'not_evaluable', 'result_missing'] as const

export type KpiSignalsBucket = {
  activations: number
  settled: number
  won: number
  lost: number
  pending: number
  not_evaluable?: number
  win_rate: number | null
  avg_book_odds_all: number | null
  avg_book_odds_won: number | null
  quota_void: number | null
  profit_units: number | null
  roi_pct: number | null
}

export type KpiSignalsFilters = {
  date_from: string
  date_to: string
  rating_bucket?: string
  selection_key?: string
  normalized_market?: string
  evaluation_status?: string
  country_name?: string
  league_name?: string
  only_current?: boolean
  include_diagnostics?: boolean
}

export type KpiHeatmapCell = KpiSignalsBucket & {
  selection_label: string
  rating_bucket: string
}

export type KpiSignalsSummaryResponse = {
  status: string
  filters: Record<string, unknown>
  overall: KpiSignalsBucket
  by_rating_bucket: Array<KpiSignalsBucket & { rating_bucket: string }>
  by_selection: Array<KpiSignalsBucket & { selection_label: string }>
  heatmap: {
    rows: string[]
    columns: string[]
    cells: KpiHeatmapCell[]
  }
  top: {
    best_profit: Array<Record<string, unknown>>
    best_roi: Array<Record<string, unknown>>
    worst_profit: Array<Record<string, unknown>>
  }
  diagnostics?: {
    today_fixtures_count: number
    fixtures_with_kpi_panel: number
    kpi_rows_seen: number
    kpi_signals_created: number
    kpi_rows_below_50: number
    kpi_rows_without_book_odds: number
  }
}

export type KpiSignalActivationRow = {
  id: number
  today_fixture_id: number
  provider_fixture_id: number
  scan_date: string
  kickoff: string | null
  country_name: string | null
  league_name: string | null
  home_team_name: string | null
  away_team_name: string | null
  selection_label: string
  selection_key: string
  normalized_market: string
  rating_score: number
  rating_label: string | null
  rating_bucket: string
  quota_book: number | null
  quota_cecchino: number | null
  edge_pct: number | null
  score_pct: number | null
  result_home_ht: number | null
  result_away_ht: number | null
  result_home_ft: number | null
  result_away_ft: number | null
  evaluation_status: string
  evaluation_reason: string | null
  profit_units: number | null
  stake_units: number | null
  evaluated_at: string | null
}

export type KpiSignalsActivationsResponse = {
  status: string
  total: number
  limit: number
  offset: number
  activations: KpiSignalActivationRow[]
}

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '') continue
    sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export async function getKpiSignalsSummary(filters: KpiSignalsFilters): Promise<KpiSignalsSummaryResponse> {
  return adminGetJson(`/api/cecchino/kpi-signals/summary${qs(filters)}`)
}

export async function getKpiSignalsActivations(
  filters: KpiSignalsFilters & { limit?: number; offset?: number },
): Promise<KpiSignalsActivationsResponse> {
  return adminGetJson(`/api/cecchino/kpi-signals/activations${qs(filters)}`)
}

export async function backfillKpiSignals(body: {
  date_from: string
  date_to: string
  only_missing?: boolean
  evaluate_after?: boolean
}): Promise<Record<string, unknown>> {
  return adminPostJson('/api/admin/cecchino/kpi-signals/backfill', body)
}

export async function revaluateKpiSignals(body: {
  date_from: string
  date_to: string
}): Promise<Record<string, unknown>> {
  return adminPostJson('/api/admin/cecchino/kpi-signals/revaluate', body)
}

export function buildKpiSignalsExportUrl(filters: KpiSignalsFilters): string {
  return `/api/cecchino/kpi-signals/export.csv${qs(filters)}`
}
