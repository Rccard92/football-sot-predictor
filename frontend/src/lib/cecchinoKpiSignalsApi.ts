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

export type KpiSignalsBackfillError = {
  today_fixture_id: number
  provider_fixture_id: number
  match: string
  scan_date?: string
  selection_key?: string
  kpi_row_key?: string
  error_type: string
  error: string
}

export type KpiSignalsBackfillResponse = {
  status: 'ok' | 'partial' | 'error'
  fixtures: number
  created: number
  updated: number
  deactivated: number
  evaluated: number
  skipped: number
  failed: number
  errors: KpiSignalsBackfillError[]
  code?: string
  message?: string
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
}): Promise<KpiSignalsBackfillResponse> {
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

export type EmpiricalPurchasabilityItem = {
  version?: string
  status: string
  score: number | null
  class: string
  competition_id?: number | null
  selection?: string | null
  market_key?: string | null
  label?: string | null
  today_fixture_id?: number | null
  rating?: number | null
  rating_band?: { min: number; max: number; label: string } | null
  sample_size?: number
  wins?: number
  losses?: number
  voids?: number
  win_rate?: number | null
  average_odds?: number | null
  average_break_even_probability?: number | null
  realized_margin?: number | null
  total_profit?: number | null
  roi?: number | null
  positive_periods?: number | null
  total_periods?: number | null
  stability_ratio?: number | null
  sample_confidence?: number | null
  historical_date_from?: string | null
  historical_date_to?: string | null
  reason_codes?: string[]
  explanation?: string
  cohort_scope?: 'same_competition' | 'all_competitions_fallback' | null
  local_sample_size?: number | null
  global_sample_size?: number | null
  selected_sample_size?: number | null
  competitions_in_cohort?: number[] | null
  competition_count?: number | null
  fallback_used?: boolean
  fallback_reason?: string | null
  raw_market_key?: string | null
  unsupported_reason?: string | null
}

export type EmpiricalPurchasabilityResponse = {
  version: string
  status: string
  items: Record<string, EmpiricalPurchasabilityItem>
  summary?: Record<string, unknown>
}

export async function getPurchasabilityEmpirical(params: {
  date_from: string
  date_to: string
  competition_id?: number | null
}): Promise<EmpiricalPurchasabilityResponse> {
  return adminGetJson(
    `/api/cecchino/kpi-signals/purchasability-empirical${qs({
      date_from: params.date_from,
      date_to: params.date_to,
      competition_id: params.competition_id ?? undefined,
    })}`,
    { timeoutMs: 120_000 },
  )
}
