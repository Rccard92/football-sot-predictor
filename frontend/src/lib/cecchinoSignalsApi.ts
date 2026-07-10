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
  won_with_odds?: number
  avg_won_book_odds?: number | null
  quota_void?: number | null
  void_margin?: number | null
  taken_yield_index?: number | null
  taken_profit_indicator?: number | null
}

export type SignalsDiagnostics = {
  date_from: string
  date_to: string
  today_fixtures_count: number
  eligible_fixtures_count: number
  fixtures_with_signal_matrix_count: number
  signal_activations_count: number
  current_signal_activations_count: number
  value_eligible_activations_count?: number
  evaluated_count: number
  won: number
  lost: number
  pending: number
  not_evaluable: number
  date_filter_field_used: string
  legacy_wrong_scala_mapping_count?: number
  monitoring_note?: string
  min_book_odds_thresholds?: Array<{
    target_market_key: string
    label: string
    min_book_odd: number
  }>
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
  si_cells_seen?: number
  value_passed?: number
  no_value_skipped?: number
  missing_book_quote_skipped?: number
  missing_cecchino_quote_skipped?: number
  invalid_quote_skipped?: number
  deactivated_no_value?: number
  min_book_odd_skipped?: number
  deactivated_min_book_odd?: number
  min_book_odd_threshold_applied?: number
  missing_value_quote?: number
  draw_pt_created?: number
  draw_pt_updated?: number
  draw_pt_deactivated?: number
  draw_pt_evaluated?: number
  derived_observations_created?: number
  derived_observations_deactivated?: number
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
  model_key?: string
  model_label?: string | null
  weights_display?: string | null
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
  counts_in_avg_won_odds?: boolean
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
  model_key?: string
  source_column?: string
  signal_group?: string
  league_name?: string
  country_name?: string
  evaluation_status?: string
  only_current?: boolean
  include_diagnostics?: boolean
}

export type WeightModelSummary = {
  model_key: string
  label: string
  short_label: string
  weights: string
  activations: number
  settled: number
  won: number
  lost: number
  pending: number
  win_rate: number | null
  avg_won_book_odds: number | null
  quota_void: number | null
  void_margin: number | null
  taken_profit_indicator: number | null
}

export type ModelsSummaryResponse = {
  date_from: string
  date_to: string
  default_model_key: string
  models: WeightModelSummary[]
}

export type BacktestModelsResponse = {
  status: string
  fixtures_found: number
  models_processed: string[]
  by_model: Array<{
    model_key: string
    signals_created: number
    signals_evaluated: number
    won: number
    lost: number
    pending: number
    win_rate: number | null
    avg_won_book_odds: number | null
    quota_void: number | null
    taken_profit_indicator: number | null
  }>
  warnings: string[]
}

export const CECCHINO_WEIGHT_MODEL_KEYS = ['A', 'B', 'C', 'D', 'E', 'F'] as const
export const DEFAULT_WEIGHT_MODEL_KEY = 'F'
export const SELECTED_MODEL_STORAGE_KEY = 'cecchino_signals_selected_model'

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
      model_key: filters.model_key ?? DEFAULT_WEIGHT_MODEL_KEY,
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
      model_key: filters.model_key ?? DEFAULT_WEIGHT_MODEL_KEY,
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
    model_key: filters.model_key ?? DEFAULT_WEIGHT_MODEL_KEY,
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
  refresh_signal_odds?: boolean
}): Promise<{
  status: string
  fixtures: number
  evaluated: number
  pending: number
  not_evaluable: number
  force_remap?: boolean
  backfill_summary?: SignalsBackfillResponse
  odds_refresh_summary?: { odds_refreshed: number; odds_still_missing: number; odds_skipped_no_kpi: number }
}> {
  return adminPostJson('/api/admin/cecchino/signals/revaluate', {
    date_from: params.date_from,
    date_to: params.date_to,
    force: params.force ?? false,
    sync_missing: params.sync_missing ?? false,
    force_remap: params.force_remap ?? false,
    refresh_signal_odds: params.refresh_signal_odds ?? false,
  })
}

export async function getCecchinoSignalsModelsSummary(params: {
  date_from: string
  date_to: string
}): Promise<ModelsSummaryResponse> {
  return adminGetJson<ModelsSummaryResponse>(
    `/api/admin/cecchino/signals/models-summary${qs({
      date_from: params.date_from,
      date_to: params.date_to,
    })}`,
  )
}

export async function backtestCecchinoWeightModels(params: {
  date_from: string
  date_to: string
  models?: string[]
  force?: boolean
  evaluate_after?: boolean
  use_existing_bookmaker_odds?: boolean
  refresh_bookmaker_odds?: boolean
}): Promise<BacktestModelsResponse> {
  return adminPostJson<BacktestModelsResponse>('/api/admin/cecchino/signals/backtest-models', {
    date_from: params.date_from,
    date_to: params.date_to,
    models: params.models ?? [...CECCHINO_WEIGHT_MODEL_KEYS],
    force: params.force ?? true,
    evaluate_after: params.evaluate_after ?? true,
    use_existing_bookmaker_odds: params.use_existing_bookmaker_odds ?? true,
    refresh_bookmaker_odds: params.refresh_bookmaker_odds ?? false,
  })
}

export const SIGNAL_DISPLAY_ORDER = [
  { group: 'HOME', label: '1' },
  { group: 'DRAW', label: 'X' },
  { group: 'AWAY', label: '2' },
  { group: 'ONE_X', label: '1X' },
  { group: 'X_TWO', label: 'X2' },
  { group: 'ONE_TWO', label: '1/2' },
  { group: 'DRAW_PT', label: 'X PT' },
  { group: 'UNDER_UNDER_PT', label: 'Under' },
  { group: 'OVER_OVER_PT', label: 'Over' },
] as const

export const SIGNAL_GROUPS = [
  { value: '', label: 'Tutti' },
  ...SIGNAL_DISPLAY_ORDER.map((row) => ({ value: row.group, label: row.label })),
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

export const HEATMAP_SIGNAL_ROWS = SIGNAL_DISPLAY_ORDER

export const HEATMAP_COLUMNS = ['EXCEL_D', 'EXCEL_E', 'EXCEL_F', 'EXCEL_G', 'SCALA'] as const

export type SignalMinBookOddSetting = {
  target_market_key: string
  label: string
  min_book_odd: number
  default_min_book_odd: number
  is_default: boolean
  is_enabled: boolean
}

export type SignalMinBookOddsSettingsResponse = {
  status: string
  items: SignalMinBookOddSetting[]
}

export type SignalMinBookOddsBacktestPayload = {
  date_from: string
  date_to: string
  items: { target_market_key: string; min_book_odd: number }[]
  rebuild_kpi_from_cache?: boolean
  include_xpt?: boolean
  force_remap_signals?: boolean
  evaluate_after?: boolean
}

export type SignalMinBookOddsBacktestSummary = {
  fixtures_seen: number
  signals_rebuilt: number
  si_cells_seen: number
  value_passed: number
  no_value_skipped: number
  min_book_odd_skipped: number
  deactivated_min_book_odd: number
  missing_book_quote_skipped: number
  missing_cecchino_quote_skipped: number
  invalid_quote_skipped: number
  deactivated_no_value: number
  signals_created?: number
  signals_updated?: number
  signals_deactivated?: number
  evaluated: number
  won: number
  lost: number
  pending: number
  not_evaluable: number
  models_processed?: string[]
  models_value_passed?: number
  models_min_book_odd_skipped?: number
  models_deactivated_min_book_odd?: number
}

export type SignalMinBookOddsModelsBacktest = {
  status: string
  fixtures_found: number
  models_processed: string[]
  by_model: {
    model_key: string
    signals_created: number
    sync_operations: number
  }[]
  value_passed?: number
  min_book_odd_skipped?: number
  deactivated_min_book_odd?: number
  warnings?: string[]
}

export type SignalMinBookOddsSaveAndBacktestResponse = {
  status: 'ok' | 'partial' | 'error'
  settings: SignalMinBookOddSetting[]
  backtest: SignalMinBookOddsBacktestSummary
  default_backtest?: SignalMinBookOddsBacktestSummary
  models_backtest?: SignalMinBookOddsModelsBacktest
  errors: string[]
}

export function formatMinBookOddsBacktestMessage(
  summary: SignalMinBookOddsBacktestSummary,
): string {
  const models = summary.models_processed?.length
    ? ` Modelli ${summary.models_processed.join(', ')} ricalcolati.`
    : ''
  return (
    `Ricalcolo completato: ${summary.si_cells_seen} celle SI, ` +
    `${summary.value_passed} a valore (default), ` +
    `${summary.min_book_odd_skipped} esclusi sotto soglia, ` +
    `${summary.deactivated_min_book_odd} disattivati.` +
  `${models}`
  )
}

export function formatMinBookOddsBacktestPanelMessage(
  summary: SignalMinBookOddsBacktestSummary,
  status: 'ok' | 'partial' | 'error',
): string {
  const modelsLabel =
    summary.models_processed && summary.models_processed.length > 0
      ? ` Modelli ${summary.models_processed.join('-')} ricalcolati.`
      : ''
  const base =
    `Ricalcolo completato: ${summary.si_cells_seen} celle SI, ` +
    `${summary.value_passed} segnali a valore, ` +
    `${summary.min_book_odd_skipped} esclusi sotto soglia minima, ` +
    `${summary.deactivated_min_book_odd} disattivati.` +
    modelsLabel
  if (status === 'partial') {
    return `${base} Completato con avvisi.`
  }
  if (
    summary.si_cells_seen > 0 &&
    summary.value_passed === 0 &&
    summary.min_book_odd_skipped === 0 &&
    summary.deactivated_min_book_odd === 0
  ) {
    return (
      'Nessun nuovo segnale rientrato: le partite erano bloccate da formula NO, ' +
      'quota book < quota Cecchino o quote mancanti.' +
      modelsLabel
    )
  }
  return base
}

export async function getSignalMinBookOddsSettings(): Promise<SignalMinBookOddsSettingsResponse> {
  return adminGetJson<SignalMinBookOddsSettingsResponse>(
    '/api/admin/cecchino/signal-min-book-odds',
  )
}

export async function updateSignalMinBookOddsSettings(
  items: { target_market_key: string; min_book_odd: number }[],
): Promise<SignalMinBookOddsSettingsResponse & { updated?: number }> {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const prefix = String(base).replace(/\/$/, '')
  const res = await fetch(`${prefix}/api/admin/cecchino/signal-min-book-odds`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  })
  const parsed = await res.json()
  if (!res.ok) {
    throw new Error(parsed?.message || 'Errore salvataggio soglie')
  }
  return parsed
}

export async function resetSignalMinBookOddsDefaults(): Promise<SignalMinBookOddsSettingsResponse> {
  return adminPostJson<SignalMinBookOddsSettingsResponse>(
    '/api/admin/cecchino/signal-min-book-odds/reset-defaults',
    {},
  )
}

export async function saveSignalMinBookOddsAndBacktest(
  payload: SignalMinBookOddsBacktestPayload,
): Promise<SignalMinBookOddsSaveAndBacktestResponse> {
  return adminPostJson<SignalMinBookOddsSaveAndBacktestResponse>(
    '/api/admin/cecchino/signal-min-book-odds/save-and-backtest',
    payload,
    { timeoutMs: 300_000 },
  )
}
