/** Client API Cecchino Lab — archivio storico Football-Data. */

import { AdminHttpError, requestJson } from './api'

const IMPORT_CONFIRM_TOKEN = 'IMPORT_CECCHINO_LAB_CSV'
const REPLACE_CONFIRM_TOKEN = 'REPLACE_CECCHINO_LAB_DATASET'

function getApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL
  if (raw === undefined || raw === null || String(raw).trim() === '') {
    throw new Error(
      'VITE_API_BASE_URL non configurata. Aggiungila in .env locale o nelle variabili di build.',
    )
  }
  return String(raw).replace(/\/+$/, '')
}

export type CecchinoLabOverview = {
  competitions_count: number
  seasons_count: number
  datasets_count: number
  matches_total: number
  matches_complete: number
  matches_incomplete: number
  anomalies_total: number
  anomalies_errors: number
  anomalies_warnings: number
  bet365_1x2_coverage_pct: number
  bet365_ou25_coverage_pct: number
  competitions: string[]
  seasons: string[]
  countries: string[]
  recent_imports: Array<{
    id: number
    dataset_id: number
    source_filename: string
    status: string
    rows_imported: number
    rows_skipped: number
    warnings_count: number
    errors_count: number
    competition_name: string | null
    season_label: string | null
    created_at: string | null
  }>
  best_quality_datasets: CecchinoLabDataset[]
  worst_quality_datasets: CecchinoLabDataset[]
  datasets_status: CecchinoLabDatasetStatus[]
  completeness: { complete: number; incomplete: number; complete_pct: number }
  is_empty: boolean
}

export type CecchinoLabDatasetStatus = {
  id: number
  competition_name: string
  season_label: string
  matches_count: number
  bet365_1x2_coverage_pct?: number | null
  bet365_ou25_coverage_pct?: number | null
  errors_count: number
  warnings_count: number
  info_count: number
  data_quality_status: string
}

export type CecchinoLabDataset = {
  id: number
  dataset_key: string
  competition_name: string
  country: string
  division_code: string | null
  season_label: string
  matches_count: number
  data_quality_status: string
  status: string
  bet365_1x2_coverage_pct?: number | null
  bet365_ou25_coverage_pct?: number | null
  anomalies_count?: number
  last_import_at?: string | null
  last_import_id?: number | null
}

export type CecchinoLabMatch = {
  id: number
  dataset_id: number
  match_date: string | null
  match_time: string | null
  home_team: string | null
  away_team: string | null
  ft_home_goals: number | null
  ft_away_goals: number | null
  ft_result: string | null
  ht_home_goals: number | null
  ht_away_goals: number | null
  ht_result: string | null
  bet365_home: number | null
  bet365_draw: number | null
  bet365_away: number | null
  bet365_over_25: number | null
  bet365_under_25: number | null
  row_quality_status: string
  competition_name: string | null
  season_label: string | null
  country: string | null
  bet365_1x2_pre_ready?: boolean
  bet365_ou25_pre_ready?: boolean
  statistics_ready?: boolean
  result_ft_ready?: boolean
}

export type CecchinoLabMatchDetail = CecchinoLabMatch & {
  referee: string | null
  home_shots: number | null
  away_shots: number | null
  home_shots_on_target: number | null
  away_shots_on_target: number | null
  home_fouls: number | null
  away_fouls: number | null
  home_corners: number | null
  away_corners: number | null
  home_yellow_cards: number | null
  away_yellow_cards: number | null
  home_red_cards: number | null
  away_red_cards: number | null
  bet365_closing_home: number | null
  bet365_closing_draw: number | null
  bet365_closing_away: number | null
  bet365_closing_over_25: number | null
  bet365_closing_under_25: number | null
  asian_handicap_home_line: number | null
  bet365_ah_home: number | null
  bet365_ah_away: number | null
  asian_handicap_closing_home_line: number | null
  bet365_closing_ah_home: number | null
  bet365_closing_ah_away: number | null
  odds_movement: Record<string, { pre: number | null; closing: number | null }>
  raw_json: Record<string, unknown> | null
  issues: Array<{
    id: number
    severity: string
    issue_code: string
    field_name: string | null
    message: string
    raw_value: string | null
  }>
}

export type CecchinoLabPreview = {
  source_filename: string | null
  headers: string[]
  recognized_columns: string[]
  missing_required_columns: string[]
  unexpected_columns: string[]
  rows_total: number
  preview_rows: Record<string, string | null>[]
  bet365_coverage: Record<string, number>
  warnings_count: number
  errors_count: number
  info_count?: number
  issues: Array<{
    severity: string
    issue_code: string
    message: string
    source_row_number: number | null
  }>
  summary: {
    importable: boolean
    rows_importable?: number
    rows_skipped?: number
  }
  file_sha256: string
  file_size_bytes: number
}

export type CecchinoLabImportResult = {
  status: string
  import_id: number
  dataset_id: number
  dataset_key: string
  rows_total: number
  rows_imported: number
  rows_skipped: number
  warnings_count: number
  errors_count: number
}

export type CecchinoLabIssue = {
  id: number
  import_id: number
  dataset_id: number
  match_id: number | null
  source_row_number: number | null
  severity: string
  issue_code: string
  field_name: string | null
  message: string
  raw_value: string | null
  created_at: string | null
  competition_name?: string | null
  season_label?: string | null
  country?: string | null
}

/** Metriche analytics Overview betting */
export type CecchinoLabMetricCount = {
  count: number
  percentage: number | null
  denominator: number
  numerator?: number
  sample_size?: number
}

export type CecchinoLabOutcomeMetric = CecchinoLabMetricCount & {
  average_bet365_pre_odds: number | null
  flat_profit_units: number | null
  flat_roi_pct: number | null
}

export type CecchinoLabGoalMetric = CecchinoLabMetricCount & {
  average_bet365_pre_odds?: number | null
  flat_profit_units?: number | null
  flat_roi_pct?: number | null
}

export type CecchinoLabFavoriteBucket = {
  bucket: string
  matches: number
  average_odds: number | null
  normalized_implied_probability: number | null
  actual_win_rate: number | null
  calibration_gap_pp: number | null
}

export type CecchinoLabLeagueRow = {
  competition_name: string
  country: string
  matches: number
  home_win_pct: number | null
  draw_pct: number | null
  away_win_pct: number | null
  over_25_pct: number | null
  under_25_pct: number | null
  btts_pct: number | null
  average_goals: number | null
  first_half_draw_pct: number | null
  favorite_hit_pct: number | null
  average_pre_margin_pct: number | null
  roi_home_pct: number | null
  roi_draw_pct: number | null
  roi_away_pct: number | null
  roi_over_25_pct: number | null
  roi_under_25_pct: number | null
  warnings_count: number
  errors_count: number
}

export type CecchinoLabInsight = {
  key: string
  title: string
  value: string
  description: string
  competition_name: string | null
  sample_size: number
  tone: 'positive' | 'neutral' | 'warning' | 'accent'
}

export type CecchinoLabAnalyticsFilters = {
  season_label?: string
  country?: string
  competition?: string
  dataset_id?: number
}

export type CecchinoLabQualityExportFilters = {
  format: 'csv' | 'json'
  scope: 'filtered' | 'all'
  severity?: string
  issue_code?: string
  dataset_id?: number
  competition?: string
  season_label?: string
}

export type CecchinoLabAnalyticsOverview = {
  available_filters: {
    seasons: string[]
    countries: string[]
    competitions: Array<{ name: string; country: string }>
  }
  applied_filters: {
    season_label: string | null
    country: string | null
    competition: string | null
    dataset_id: number | null
  }
  sample: {
    matches_total: number
    competitions_count: number
    seasons_count: number
  }
  summary: {
    matches_total: number
    competitions_count: number
    seasons_count: number
    total_goals: number
    average_goals_per_match: number | null
    average_home_goals: number | null
    average_away_goals: number | null
    favorite_hit_rate: number | null
    bet365_1x2_coverage_pct: number | null
    anomalies_errors: number
    anomalies_warnings: number
    completeness_pct: number | null
    best_flat_roi: { label: string; roi: number; sample_size: number } | null
    average_pre_closing_margin_pct: number | null
  }
  outcomes_1x2: {
    home: CecchinoLabOutcomeMetric
    draw: CecchinoLabOutcomeMetric
    away: CecchinoLabOutcomeMetric
  }
  goals: {
    over_15: CecchinoLabGoalMetric
    over_25: CecchinoLabGoalMetric
    under_25: CecchinoLabGoalMetric
    under_35: CecchinoLabGoalMetric
    btts_yes: CecchinoLabGoalMetric
    btts_no: CecchinoLabGoalMetric
    score_0_0: CecchinoLabGoalMetric
    team_blank: CecchinoLabGoalMetric
    goals_ge_4: CecchinoLabGoalMetric
    goals_ge_5: CecchinoLabGoalMetric
  }
  first_half: {
    draw: CecchinoLabMetricCount
    over_05: CecchinoLabMetricCount
    over_15: CecchinoLabMetricCount
    under_15: CecchinoLabMetricCount
    score_0_0: CecchinoLabMetricCount
    average_goals: number | null
    pct_of_ft_goals: number | null
    sample_size: number
  }
  favorite: {
    unique_count: number
    wins: number
    losses: number
    hit_rate: number | null
    average_odds: number | null
    home_favorite_pct: number | null
    away_favorite_pct: number | null
    draw_favorite_pct: number | null
    buckets: CecchinoLabFavoriteBucket[]
  }
  margins: {
    average_pre_closing_margin_pct: number | null
    median_pre_closing_margin_pct: number | null
    average_closing_margin_pct: number | null
    median_closing_margin_pct: number | null
    average_pre_to_closing_delta_pp: number | null
    by_competition: Array<{
      competition_name: string
      average_pre_closing_margin_pct: number | null
      sample_size: number
    }>
    sample_size_pre: number
    sample_size_closing: number
  }
  odds_movement: {
    average_home_movement_pct: number | null
    average_draw_movement_pct: number | null
    average_away_movement_pct: number | null
    favorite_shortened_pct: number | null
    winning_selection_shortened_pct: number | null
    average_winner_movement_pct: number | null
    sample_size: number
    distribution: Array<{ bucket: string; count: number; percentage: number | null }>
  }
  longest_odds_hit: {
    count: number
    percentage: number | null
    average_winning_odds: number | null
    top_competition: {
      competition_name: string
      percentage: number | null
      sample_size: number
    } | null
    record_match: {
      match_id: number
      match_date: string | null
      competition_name: string
      season_label: string
      home_team: string | null
      away_team: string | null
      result: string
      selection: string
      odds: number | null
    } | null
    sample_size: number
  }
  leagues: CecchinoLabLeagueRow[]
  insights: CecchinoLabInsight[]
  is_empty: boolean
}


async function postFormData<T>(path: string, form: FormData): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, { method: 'POST', body: form })
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
    throw new AdminHttpError(
      res.status,
      (body as { message?: string })?.message || res.statusText,
      body,
    )
  }
  if (body && typeof body === 'object' && 'status' in body && (body as { status: string }).status === 'error') {
    throw new AdminHttpError(
      res.status,
      (body as { message?: string }).message || 'Errore import',
      body,
    )
  }
  return body as T
}

async function postJson<T>(path: string, payload?: unknown): Promise<T> {
  const base = getApiBase()
  const p = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(`${base}${p}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  })
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
    throw new AdminHttpError(
      res.status,
      (body as { message?: string })?.message || res.statusText,
      body,
    )
  }
  if (body && typeof body === 'object' && 'status' in body && (body as { status: string }).status === 'error') {
    throw new AdminHttpError(
      res.status,
      (body as { message?: string }).message || 'Errore richiesta',
      body,
    )
  }
  return body as T
}

export function getCecchinoLabOverview(): Promise<CecchinoLabOverview> {
  return requestJson('/api/cecchino-lab/overview')
}

export function getCecchinoLabAnalyticsOverview(
  filters?: CecchinoLabAnalyticsFilters,
): Promise<CecchinoLabAnalyticsOverview> {
  const q = new URLSearchParams()
  if (filters?.season_label) q.set('season_label', filters.season_label)
  if (filters?.country) q.set('country', filters.country)
  if (filters?.competition) q.set('competition', filters.competition)
  if (filters?.dataset_id != null) q.set('dataset_id', String(filters.dataset_id))
  const qs = q.toString()
  return requestJson(`/api/cecchino-lab/analytics/overview${qs ? `?${qs}` : ''}`)
}

export async function downloadCecchinoLabQualityExport(
  filters: CecchinoLabQualityExportFilters,
): Promise<void> {
  const q = new URLSearchParams()
  q.set('format', filters.format)
  q.set('scope', filters.scope)
  if (filters.scope === 'filtered') {
    if (filters.severity) q.set('severity', filters.severity)
    if (filters.issue_code) q.set('issue_code', filters.issue_code)
    if (filters.dataset_id != null) q.set('dataset_id', String(filters.dataset_id))
    if (filters.competition) q.set('competition', filters.competition)
    if (filters.season_label) q.set('season_label', filters.season_label)
  }
  const base = getApiBase()
  const res = await fetch(`${base}/api/cecchino-lab/data-quality/issues/export?${q.toString()}`)
  if (!res.ok) {
    let message = res.statusText
    try {
      const body = await res.json()
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="?([^"]+)"?/i.exec(cd)
  const fallback = `cecchino_lab_quality.${filters.format === 'csv' ? 'csv' : 'json'}`
  const filename = match?.[1] || fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}


export function getCecchinoLabDatasets(params?: {
  country?: string
  competition?: string
  season?: string
  quality_status?: string
}): Promise<{ items: CecchinoLabDataset[]; total: number }> {
  const q = new URLSearchParams()
  if (params?.country) q.set('country', params.country)
  if (params?.competition) q.set('competition', params.competition)
  if (params?.season) q.set('season', params.season)
  if (params?.quality_status) q.set('quality_status', params.quality_status)
  const qs = q.toString()
  return requestJson(`/api/cecchino-lab/datasets${qs ? `?${qs}` : ''}`)
}

export function getCecchinoLabDataset(id: number): Promise<CecchinoLabDataset & { imports: unknown[] }> {
  return requestJson(`/api/cecchino-lab/datasets/${id}`)
}

export function getCecchinoLabMatches(params: Record<string, string | number | boolean | undefined>): Promise<{
  items: CecchinoLabMatch[]
  total: number
  page: number
  page_size: number
}> {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '') continue
    q.set(k, String(v))
  }
  return requestJson(`/api/cecchino-lab/matches?${q.toString()}`)
}

export function getCecchinoLabMatch(id: number): Promise<CecchinoLabMatchDetail> {
  return requestJson(`/api/cecchino-lab/matches/${id}`)
}

export function getCecchinoLabIssues(params: Record<string, string | number | undefined>): Promise<{
  items: CecchinoLabIssue[]
  total: number
  page: number
  page_size: number
  top_issue_codes: Array<{ issue_code: string; count: number }>
  severity_counts: Record<string, number>
}> {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === '') continue
    q.set(k, String(v))
  }
  return requestJson(`/api/cecchino-lab/data-quality/issues?${q.toString()}`)
}

export type LabCompetitionCatalogItem = {
  key: string
  display_name: string
  country: string
  division_code: string
  timezone: string
}

export type ImportMeta = {
  competition_key: string
  season_label: string
}

export const LAB_SEASON_OPTIONS = [
  '2025/2026',
  '2024/2025',
  '2023/2024',
  '2022/2023',
  '2021/2022',
  '2020/2021',
] as const

export function getCecchinoLabCompetitions(): Promise<{ items: LabCompetitionCatalogItem[] }> {
  return requestJson('/api/cecchino-lab/catalog/competitions')
}

export function previewCecchinoLabCsv(file: File, meta: ImportMeta): Promise<CecchinoLabPreview> {
  const form = new FormData()
  form.append('file', file)
  form.append('competition_key', meta.competition_key)
  form.append('season_label', meta.season_label)
  return postFormData('/api/admin/cecchino-lab/imports/preview', form)
}

export type BatchImportStatus =
  | 'ready'
  | 'ready_with_warnings'
  | 'blocked'
  | 'already_imported'
  | 'duplicate_in_batch'
  | 'duplicate_competition_in_batch'
  | 'dataset_already_exists'

export type CecchinoLabBatchPreviewItem = {
  client_file_id: string
  filename: string
  file_sha256: string
  file_size_bytes: number
  division_code: string | null
  competition_key: string | null
  competition_name: string | null
  country: string | null
  timezone: string | null
  season_label: string
  rows_total: number | null
  rows_importable: number | null
  rows_skipped: number | null
  errors_count: number
  warnings_count: number
  info_count: number
  bet365_coverage: Record<string, number>
  mapping_status: string
  import_status: BatchImportStatus
  dataset_id: number | null
  blocking_reason: string | null
  issues: Array<{
    severity: string
    issue_code: string
    message: string
    source_row_number: number | null
  }>
  preview_rows: Record<string, string | null>[]
  recognized_columns: string[]
  unexpected_columns: string[]
  missing_required_columns: string[]
}

export type CecchinoLabBatchPreview = {
  status: string
  season_label: string
  files_total: number
  ready_count: number
  warning_count: number
  blocked_count: number
  already_imported_count: number
  rows_total: number
  rows_importable: number
  items: CecchinoLabBatchPreviewItem[]
}

export function previewCecchinoLabBatch(
  files: File[],
  seasonLabel: string,
): Promise<CecchinoLabBatchPreview> {
  const form = new FormData()
  form.append('season_label', seasonLabel)
  for (const file of files) {
    form.append('files', file)
  }
  return postFormData('/api/admin/cecchino-lab/imports/batch/preview', form)
}

export function batchImportStatusLabel(status: BatchImportStatus | string): string {
  switch (status) {
    case 'ready':
      return 'Pronto'
    case 'ready_with_warnings':
      return 'Pronto con warning'
    case 'already_imported':
      return 'Già importato'
    case 'duplicate_in_batch':
    case 'duplicate_competition_in_batch':
      return 'Duplicato'
    case 'dataset_already_exists':
      return 'Già presente'
    case 'blocked':
      return 'Bloccato'
    default:
      if (status === 'unknown_division' || status === 'missing_division') return 'Divisione sconosciuta'
      return status || '—'
  }
}

export function batchImportStatusBadgeClass(status: BatchImportStatus | string): string {
  if (status === 'ready') return 'lab-badge-ok'
  if (status === 'ready_with_warnings') return 'lab-badge-warn'
  if (status === 'already_imported' || status === 'dataset_already_exists') return 'lab-badge-muted'
  if (
    status === 'duplicate_in_batch' ||
    status === 'duplicate_competition_in_batch' ||
    status === 'blocked'
  ) {
    return 'lab-badge-err'
  }
  return 'lab-badge-muted'
}

export function isBatchItemReady(status: BatchImportStatus | string): boolean {
  return status === 'ready' || status === 'ready_with_warnings'
}

export function countBatchReadyItems(items: Array<{ import_status: string }>): number {
  return items.filter((i) => isBatchItemReady(i.import_status)).length
}

export function importCecchinoLabCsv(file: File, meta: ImportMeta): Promise<CecchinoLabImportResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('competition_key', meta.competition_key)
  form.append('season_label', meta.season_label)
  form.append('confirm', IMPORT_CONFIRM_TOKEN)
  return postFormData('/api/admin/cecchino-lab/imports', form)
}

export type CecchinoLabReplaceResult = {
  status: string
  dataset_id: number
  dataset_key: string
  competition_name: string
  season_label: string
  previous_matches_count: number
  import_id: number
  rows_total: number
  rows_imported: number
  rows_skipped: number
  warnings_count: number
  errors_count: number
  info_count: number
  data_quality_status: string
}

export function replaceCecchinoLabDataset(datasetId: number, file: File): Promise<CecchinoLabReplaceResult> {
  const form = new FormData()
  form.append('file', file)
  form.append('confirm', REPLACE_CONFIRM_TOKEN)
  return postFormData(`/api/admin/cecchino-lab/datasets/${datasetId}/replace`, form)
}

export const HISTORICAL_SCAN_CONFIRM_TOKEN = 'RUN_CECCHINO_LAB_HISTORICAL_SCAN'
export const DERIVED_REBUILD_CONFIRM_TOKEN = 'REBUILD_CECCHINO_LAB_DERIVED_V3'
export const DEFAULT_HISTORICAL_SEASON = '2021/2022'

export type HistoricalDerivedRefresh = {
  status?: string | null
  applied_at?: string | null
  applied_git_commit?: string | null
  formula_version?: string | null
  consensus_policy_version?: string | null
  audit_version?: string | null
  market_registry_count?: number | null
  source_run_git_commit?: string | null
  external_api_calls?: number | null
  full_scan_restarted?: boolean | null
  snapshots_rebuilt?: number | null
}

export type HistoricalDerivedRebuildResult = {
  status: string
  schema_version?: string
  run_id: number
  run_status?: string | null
  snapshots_found: number
  snapshots_rebuildable: number
  snapshots_partial: number
  snapshots_blocked: number
  market_results_to_replace: number
  signals_to_rebuild: number
  kpi_to_rebuild: number
  missing_inputs_by_reason: Record<string, number>
  external_api_calls: number
  full_scan_required: boolean
  full_scan_restarted?: boolean
  signal_contract: {
    formula_version?: string
    consensus_policy_version?: string
    audit_version?: string
    formula_label?: string
    [key: string]: unknown
  }
  formula_version?: string
  consensus_policy_version?: string
  audit_version?: string
  market_registry_count: number
  confirm_token_required: string
  derived_refresh?: HistoricalDerivedRefresh | null
  dry_run?: boolean
  snapshots_rebuilt?: number
  classifications?: Array<{
    snapshot_id: number
    classification: string
    reasons: string[]
    signals_rebuildable?: boolean
    market_results_rebuildable?: boolean
  }>
  rebuilt?: Array<Record<string, unknown>>
  run_active?: boolean
}

export function historicalRunDerivedRebuild(
  runId: number,
  options?: { dry_run?: boolean; confirm?: string | null },
): Promise<HistoricalDerivedRebuildResult> {
  return postJson(`/api/admin/cecchino-lab/historical/runs/${runId}/derived-rebuild`, {
    dry_run: options?.dry_run ?? true,
    confirm: options?.confirm ?? null,
  })
}

export type HistoricalScanPreflight = {
  season_label: string
  status: 'ready' | 'ready_with_warnings' | 'blocked' | string
  datasets_found: Array<{
    id: number
    dataset_key: string
    competition_name: string
    country: string
    matches_count: number
    data_quality_status: string
  }>
  competitions_found: string[]
  matches_total: number
  matches_with_valid_kickoff?: number
  matches_with_ft?: number
  matches_with_ht?: number
  bet365_1x2_pre_coverage?: number
  bet365_1x2_closing_coverage?: number
  bet365_ou25_pre_coverage?: number
  bet365_ou25_closing_coverage?: number
  quote_counts?: { real: number; derived: number; not_available: number }
  blocking_anomalies?: Array<{ code: string; message: string }>
  warnings?: Array<{ code: string; message: string }>
  module_availability?: Record<string, { status: string; note?: string }>
  market_availability?: Record<string, { status: string; expected_coverage_pct?: number }>
}

export type HistoricalScanRun = {
  id: number
  season_label: string
  status: string
  scan_version: string
  requested_at: string | null
  started_at: string | null
  completed_at: string | null
  current_dataset_id: number | null
  current_match_id: number | null
  current_competition: string | null
  matches_total: number
  matches_processed: number
  matches_eligible_core: number
  matches_excluded: number
  matches_error: number
  progress_pct: number | null
  progress_detail?: {
    competitions_completed?: number
    competitions_total?: number
    eligible_collected?: number
    eligible_target?: number
    matches_processed?: number
    matches_excluded?: number
    matches_error?: number
    current_competition?: string | null
    eligible_in_current_competition?: number | null
    eligible_per_competition_target?: number | null
  } | null
  preflight?: HistoricalScanPreflight | null
  summary?: Record<string, unknown> | null
  error?: Record<string, unknown> | null
  source_git_commit?: string | null
  source_git_commit_source?: string | null
  source_revision_status?: string | null
  cancel_requested?: boolean
  run_scope?: 'pilot' | 'balanced_pilot' | 'full' | string
  is_partial_run?: boolean
  not_full_season_report?: boolean
  max_matches?: number | null
  pilot_strategy?: string | null
  eligible_per_competition?: number | null
  module_policy?: Record<string, unknown> | null
}

export function preflightHistoricalScan(seasonLabel: string): Promise<HistoricalScanPreflight> {
  return postJson('/api/admin/cecchino-lab/historical-scans/preflight', {
    season_label: seasonLabel,
  })
}

export const HISTORICAL_SCAN_PILOT_MAX_MATCHES = 200
export const HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP = 20

export type HistoricalReportMode =
  | 'ai_summary'
  | 'competition'
  | 'module'
  | 'full_archive'

export type HistoricalReportModule =
  | 'markets'
  | 'signals'
  | 'goal_intensity'
  | 'purchasability'
  | 'balance'

export function startHistoricalScan(
  seasonLabel: string,
  options?: {
    maxMatches?: number | null
    pilotStrategy?: 'max_matches' | 'eligible_per_competition' | null
    eligiblePerCompetition?: number | null
  },
): Promise<HistoricalScanRun> {
  const body: Record<string, unknown> = {
    season_label: seasonLabel,
    confirm: HISTORICAL_SCAN_CONFIRM_TOKEN,
  }
  if (options?.pilotStrategy) {
    body.pilot_strategy = options.pilotStrategy
  }
  if (options && 'eligiblePerCompetition' in (options || {})) {
    body.eligible_per_competition = options.eligiblePerCompetition ?? null
  }
  if (options && 'maxMatches' in options) {
    body.max_matches = options.maxMatches ?? null
  }
  return postJson('/api/admin/cecchino-lab/historical-scans', body)
}

export function historicalScanScopeLabel(run: HistoricalScanRun): string {
  if (run.run_scope === 'balanced_pilot' || run.pilot_strategy === 'eligible_per_competition') {
    const n = run.eligible_per_competition ?? HISTORICAL_SCAN_BALANCED_ELIGIBLE_PER_COMP
    return `Pilota bilanciato (${n} eleggibili/campionato)`
  }
  if (run.is_partial_run || run.run_scope === 'pilot') {
    const n = run.max_matches ?? HISTORICAL_SCAN_PILOT_MAX_MATCHES
    return `Test tecnico (max ${n})`
  }
  return 'Completa'
}

export function listHistoricalScans(seasonLabel?: string): Promise<HistoricalScanRun[]> {
  const q = seasonLabel ? `?season_label=${encodeURIComponent(seasonLabel)}` : ''
  return requestJson(`/api/cecchino-lab/historical-scans${q}`)
}

export function getHistoricalScan(runId: number): Promise<HistoricalScanRun> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}`)
}

export function resumeHistoricalScan(runId: number): Promise<HistoricalScanRun> {
  return postJson(`/api/admin/cecchino-lab/historical-scans/${runId}/resume`)
}

export function cancelHistoricalScan(runId: number): Promise<HistoricalScanRun> {
  return postJson(`/api/admin/cecchino-lab/historical-scans/${runId}/cancel`)
}

export function getHistoricalScanSummary(runId: number): Promise<Record<string, unknown>> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}/summary`)
}

async function readHttpErrorMessage(res: Response, fallback: string): Promise<string> {
  let message = fallback
  try {
    const body = (await res.json()) as {
      detail?: string | { message?: string; detail?: string }
      message?: string
    }
    if (typeof body?.detail === 'string') {
      message = body.detail
    } else if (body?.detail && typeof body.detail === 'object') {
      message =
        (typeof body.detail.message === 'string' && body.detail.message) ||
        (typeof body.detail.detail === 'string' && body.detail.detail) ||
        message
    } else if (typeof body?.message === 'string') {
      message = body.message
    }
  } catch {
    /* ignore non-JSON bodies */
  }
  return message
}

export function formatHistoricalDownloadError(err: unknown, fallback = 'Download fallito'): string {
  if (err instanceof AdminHttpError) {
    if (err.status === 409) {
      return (
        err.message ||
        'Acquistabilità V3 non disponibile: completa il replay prima di scaricare il report.'
      )
    }
    return err.message || fallback
  }
  if (err instanceof Error && err.message) return err.message
  return fallback
}

export async function downloadHistoricalScanReport(
  runId: number,
  options?: {
    mode?: HistoricalReportMode
    competition?: string
    module?: HistoricalReportModule
  },
): Promise<void> {
  if (options?.mode === 'module' && options.module === 'purchasability') {
    await downloadHistoricalRunOfficialPurchasabilityReport(runId, 'analysis')
    return
  }
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', options?.mode ?? 'ai_summary')
  if (options?.competition) params.set('competition', options.competition)
  if (options?.module) params.set('module', options.module)
  const res = await fetch(
    `${base}/api/cecchino-lab/historical-scans/${runId}/report?${params.toString()}`,
  )
  if (!res.ok) {
    const message = await readHttpErrorMessage(
      res,
      `Download report fallito (${res.status})`,
    )
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] || `cecchino_lab_ai_report_run_${runId}.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function historicalScanStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: 'In coda',
    running: 'In esecuzione',
    completed: 'Completata',
    completed_with_warnings: 'Completata con warning',
    failed: 'Fallita',
    cancelled: 'Annullata',
    ready: 'Pronta',
    ready_with_warnings: 'Pronta con warning',
    blocked: 'Bloccata',
  }
  return map[status] || status
}

export function isHistoricalScanActive(status: string): boolean {
  return status === 'pending' || status === 'running'
}

export function quoteLegendClass(kind: 'real' | 'derived' | 'unavailable'): string {
  if (kind === 'real') return 'lab-quote-real'
  if (kind === 'derived') return 'lab-quote-derived'
  return 'lab-quote-na'
}

export { IMPORT_CONFIRM_TOKEN, REPLACE_CONFIRM_TOKEN }

/** Pure helpers for unit tests */
export function formatOdd(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—'
  return v.toFixed(2)
}

/** Null / non calcolato → em dash (mai 0,00 fittizio). */
export function formatNullableNumber(
  v: number | null | undefined,
  digits = 2,
): string {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(digits)
}

export function patternSampleBadgeLabel(status: string | null | undefined): string {
  switch (status) {
    case 'small_sample':
      return 'Campione insufficiente'
    case 'exploratory_only':
      return 'Esplorativo'
    case 'descriptive_only':
      return 'Descrittivo'
    case 'candidate_for_validation':
    case 'candidate_for_review':
      return 'Candidato da validare'
    case 'coverage_diagnostic':
      return 'Diagnostica copertura'
    default:
      return status || '—'
  }
}

export function patternStabilityBadgeLabel(
  category: string | null | undefined,
): string {
  switch (category) {
    case 'insufficient_evidence':
      return 'Insufficiente'
    case 'concentrated':
      return 'Concentrata'
    case 'inconsistent':
      return 'Incoerente'
    case 'directionally_consistent':
      return 'Coerente'
    case 'stable_candidate':
      return 'Candidata stabile'
    default:
      return category || '—'
  }
}

export function matchOddsColumnLabel(field: 'home' | 'draw' | 'away'): string {
  if (field === 'home') return '1'
  if (field === 'draw') return 'X'
  return '2'
}

export function qualityBadgeClass(status: string): string {
  if (status === 'complete') return 'lab-badge-ok'
  if (status === 'complete_with_warnings') return 'lab-badge-warn'
  if (status === 'error' || status === 'poor') return 'lab-badge-err'
  if (status === 'warning' || status === 'partial') return 'lab-badge-warn'
  return 'lab-badge-muted'
}

export function isOverviewEmpty(overview: CecchinoLabOverview | null): boolean {
  return !overview || overview.is_empty === true
}

export function formatAnomaliesHint(errors: number, warnings: number): string {
  return `${errors} errori · ${warnings} warning`
}

export function replaceDatasetConfirmMessage(
  competitionName: string,
  seasonLabel: string,
): string {
  return (
    `Stai per sostituire esclusivamente il CSV di ${competitionName} ${seasonLabel}. ` +
    `Serie A, Championship e gli altri dataset non saranno modificati.`
  )
}

/* ─── Historical run dashboard (read-only analytics) ─── */

export type HistoricalRunFilters = {
  competition?: string
  date_from?: string
  date_to?: string
  market_key?: string
  rating_band?: string
  purchasability_band?: string
  quote_quality?: string
  signal_model?: string
  signal_active?: string
  balance_class?: string
  goal_intensity_status?: string
  purchasability_status?: string
  eligibility_status?: string
}

export type HistoricalRunDashboardOverview = {
  run: {
    run_id: number
    season_label: string
    scope?: string | null
    status: string
    scan_version: string
    source_git_commit?: string | null
    source_git_commit_source?: string | null
    source_revision_status?: string | null
    started_at?: string | null
    completed_at?: string | null
    bookmaker_storico: string
    bookmaker_today_operativo: string
    is_partial_run?: boolean
    not_full_season_report?: boolean
    run_scope?: string | null
  }
  is_provisional: boolean
  data_as_of: string
  scan_source_git_commit?: string | null
  analytics_runtime_git_commit?: string | null
  analytics_runtime_git_commit_source?: string | null
  analytics_runtime_revision_status?: string | null
  analytics_aggregation_version?: string
  filters: HistoricalRunFilters
  kpis: Record<string, unknown>
  progress: Record<string, unknown>
  module_coverage: Record<string, HistoricalRunModuleCoverage>
  market_summary: Record<string, unknown>
  warnings: string[]
  active_eligible_sample?: number
}

export type HistoricalRunModuleCoverage = {
  complete: number
  partial: number
  unavailable: number
  coverage_pct: number
  warnings: string[]
  observation_status: string
}

export type HistoricalRunDashboardMarket = {
  market_key: string
  label: string
  period?: string | null
  line?: string | null
  sample_size: number
  wins: number
  losses: number
  hit_rate: number | null
  outcome_base_rate: number | null
  average_cecchino_probability: number | null
  median_cecchino_probability: number | null
  with_cecchino_probability?: number
  with_cecchino_fair_quote?: number
  with_cecchino_quote?: number
  calibration_gap: number | null
  brier_score: number | null
  average_rating: number | null
  rating_available_count: number
  with_rating?: number
  signal_active_count: number
  matches_with_signal: number
  real_quote_count: number
  derived_quote_count: number
  unavailable_quote_count: number
  quote_count_reconciliation_ok?: boolean
  average_real_odds: number | null
  average_derived_odds: number | null
  real_profit_1u: number | null
  real_roi_pct: number | null
  synthetic_profit_1u: number | null
  synthetic_roi_pct: number | null
  max_losing_streak: number
  competitions_count: number
  chronological_stability: unknown
  warnings: string[]
  confidence_status?: string
}

export type HistoricalRunRatingCell = {
  market_key: string
  rating_band: string
  sample_size: number
  wins: number
  losses: number
  hit_rate: number | null
  average_odds: number | null
  real_quote_count: number
  unavailable_quote_count?: number
  real_profit_1u: number | null
  real_roi_pct: number | null
  derived_quote_count: number
  synthetic_profit_1u: number | null
  synthetic_roi_pct: number | null
  competitions_count: number
  confidence_status: string
}

export type HistoricalPurchasabilityGateStatus =
  | 'accepted'
  | 'rejected_non_positive_edge'
  | 'rejected_non_positive_probability_advantage'
  | 'rejected_multiple_non_positive_components'
  | 'not_evaluated_insufficient_history'
  | 'unsupported_market'
  | 'unavailable_inputs'
  | 'unknown_legacy'
  | string

export type HistoricalPurchasabilityDecisionGroup =
  | 'ONE_X_TWO_REAL'
  | 'GOALS_FT_2_5_REAL'
  | 'DOUBLE_CHANCE_DERIVED'
  | string

export type HistoricalPurchasabilityEvaluation = {
  purchasability_evaluation_id?: string
  run_id?: number
  snapshot_id?: number
  match_snapshot_id?: number
  lab_match_id?: number | null
  dataset_id?: number | null
  competition_name?: string | null
  season_label?: string | null
  kickoff_at?: string | null
  chronological_order?: number | null
  home_team?: string | null
  away_team?: string | null
  home_score_ft?: number | null
  away_score_ft?: number | null
  home_score_ht?: number | null
  away_score_ht?: number | null
  eligibility_status?: string | null
  settlement_status?: string | null
  market_key?: string | null
  market_label?: string | null
  period?: string | null
  line?: string | null
  quote_quality?: string | null
  is_real_book_quote?: boolean | null
  is_derived_quote?: boolean | null
  real_book_odds?: number | null
  derived_odds?: number | null
  prob_book_raw?: number | null
  prob_book_fair?: number | null
  prob_cecchino?: number | null
  quota_cecchino?: number | null
  rating?: number | null
  edge_pct?: number | null
  vantaggio_prob?: number | null
  signal_active_current_F?: boolean | null
  won?: boolean | null
  evaluation_status?: string | null
  result_reason?: string | null
  profit_1u_real?: number | null
  profit_1u_synthetic?: number | null
  market_join_status?: string | null
  final_score?: number | null
  persisted_score?: number | null
  score_class?: string | null
  positive_value_gate?: Record<string, unknown> | null
  gate_status?: HistoricalPurchasabilityGateStatus | null
  gate_reasons?: string[]
  score_zero_semantics?: string | null
  diagnostic_ungated_score?: number | null
  diagnostic_ungated_score_source?: string | null
  phase_1_score?: number | null
  phase_2_score?: number | null
  formula_version?: string | null
  parity_status?: string | null
  formula_recomputed?: boolean
}

export type HistoricalPurchasabilityDecision = {
  decision_id: string
  run_id: number
  snapshot_id: number
  competition_name?: string | null
  kickoff_at?: string | null
  decision_group: HistoricalPurchasabilityDecisionGroup
  candidate_markets: string[]
  evaluated_markets_count: number
  accepted_markets_count: number
  rejected_markets_count: number
  highest_final_score?: number | null
  selected_market_key?: string | null
  selected_score?: number | null
  selected_gate_status?: string | null
  selection_tied: boolean
  tied_market_keys: string[]
  selection_rule: string
  selected_quote_quality?: string | null
  selected_odds?: number | null
  selected_won?: boolean | null
  selected_profit_1u_real?: number | null
  selected_profit_1u_synthetic?: number | null
  performance_available?: boolean
  best_diagnostic_ungated_score?: number | null
  best_diagnostic_ungated_market_key?: string | null
  performance_type?: string
  not_real_bet365_strategy?: boolean
  diagnostic_only: boolean
  not_a_production_strategy: boolean
}

export type HistoricalPurchasabilityDriftBucket = {
  evaluations_count?: number
  computed_count?: number
  insufficient_history_count?: number
  unsupported_count?: number
  unavailable_count?: number
  gate_accepted_count?: number
  gate_rejected_count?: number
  gate_accepted_pct?: number | null
  score_zero_count?: number
  score_zero_pct?: number | null
  score_ge_80_count?: number
  score_ge_80_pct?: number | null
  mean_accepted_score?: number | null
  median_accepted_score?: number | null
  p10_accepted_score?: number | null
  p90_accepted_score?: number | null
  mean_normalization_sample_size?: number | null
  min_normalization_sample_size?: number | null
  max_normalization_sample_size?: number | null
  distinct_profile_hashes?: number
  first_profile_hash?: string | null
  last_profile_hash?: string | null
  cap_diagnostics_available?: boolean
}

export type HistoricalPurchasabilityMarketJoinDiagnostics = {
  evaluations_total: number
  matched_count: number
  missing_count: number
  ambiguous_count: number
  invalid_count: number
  matched_pct: number | null
  by_market_key?: Record<string, Record<string, number>>
  by_competition?: Record<string, Record<string, number>>
  matched_plus_missing_plus_ambiguous_plus_invalid_equals_total?: boolean
}

export type HistoricalPurchasabilityExportReconciliation = {
  market_evaluations: number
  unique_evaluation_ids: number
  duplicate_evaluation_ids: number
  evaluation_id_unique: boolean
  matched_plus_missing_plus_ambiguous_plus_invalid_equals_total: boolean
  source_snapshots_unchanged: boolean
}

export type HistoricalPurchasabilityExportSummary = {
  export_schema_version: string
  evaluations_total: number
  evaluations_by_status?: Record<string, number>
  gate_status_counts?: Record<string, number>
  gate_reason_counts?: Record<string, number>
  final_score_zero_count?: number
  gate_rejected_zero_count?: number
  calculated_zero_count?: number
  diagnostic_ungated_score_available_count?: number
  market_join_diagnostics?: HistoricalPurchasabilityMarketJoinDiagnostics
  quote_quality_counts?: Record<string, number>
  decision_group_counts?: Record<string, number>
  normalization_drift_summary?: HistoricalPurchasabilityDriftBucket
  compact_export_reconciliation?: HistoricalPurchasabilityExportReconciliation
  formula_recomputed?: boolean
  run_snapshot_modified?: boolean
}

export type HistoricalPurchasabilityScoreRow = {
  market_key?: string
  gate_status?: string | null
  gate_label?: string
  final_score?: number | null
  diagnostic_ungated_score?: number | null
  rating?: number | null
  edge_pct?: number | null
  vantaggio_prob?: number | null
  quote_quality?: string | null
  real_book_odds?: number | null
  derived_odds?: number | null
  won?: boolean | null
  profit_1u_real?: number | null
  profit_1u_synthetic?: number | null
  score_class?: string | null
  competition_name?: string | null
  home_team?: string | null
  away_team?: string | null
  kickoff_at?: string | null
}

export type HistoricalRunPurchasabilityAnalytics = {
  run_id: number
  is_provisional: boolean
  bands: string[]
  distribution: Record<string, Record<string, unknown>>
  distribution_role?: string
  by_market: Array<Record<string, unknown>>
  primary_view?: string
  by_competition: Array<Record<string, unknown>>
  rating_x_purchasability: Array<Record<string, unknown>>
  complete_count: number
  partial_count: number
  unavailable_count: number
  warning?: string
  note?: string
  observation_status?: string
  execution_status?: string
  profile_sample_size?: number
  analytics_aggregation_version?: string
  purchasability_export_schema_version?: string
  observational_warning?: string
  scores_by_market?: Record<string, HistoricalPurchasabilityScoreRow[]>
  gate?: {
    accepted?: number
    rejected?: number
    other?: number
    gate_status_counts?: Record<string, number>
    gate_reason_counts?: Record<string, number>
    gate_status_by_market?: Record<string, Record<string, number>>
    gate_rejected_zero_count?: number
    blocked_label?: string
  }
  decisions_by_group?: Record<string, HistoricalPurchasabilityDecision[]>
  drift?: {
    by_month?: Record<string, HistoricalPurchasabilityDriftBucket>
    by_competition?: Record<string, HistoricalPurchasabilityDriftBucket>
    overall?: HistoricalPurchasabilityDriftBucket
  }
  evaluations_total?: number
  decisions_total?: number
  formula_recomputed?: boolean
  run_snapshot_modified?: boolean
}

/** Etichetta UI: mai «Molto Bassa» per gate rejected. */
export function purchasabilityGateDisplayLabel(
  gateStatus: string | null | undefined,
  scoreClass: string | null | undefined,
): string {
  if (gateStatus && String(gateStatus).startsWith('rejected_')) {
    return 'Bloccato dal gate'
  }
  if (gateStatus === 'accepted') {
    return scoreClass && scoreClass !== 'Molto Bassa' ? scoreClass : 'Accettato'
  }
  if (!gateStatus) return scoreClass || '—'
  return String(gateStatus)
}

export type HistoricalSignalCell = {
  signal_group: string | null
  source_column: string | null
  cell_key: string | null
  cell_label: string | null
  signal_family: string | null
  target_market: string | null
  raw_value: string | null
  threshold: number | null
  comparison_operator: string | null
  weight: number | null
  weighted_contribution: number | null
  source_version: string | null
}

export type HistoricalSignalOpportunity = {
  row_granularity: 'signal_opportunity'
  opportunity_id: string
  run_id: number
  snapshot_id: number
  match_snapshot_id?: number
  lab_match_id: number
  dataset_id: number | null
  competition_name: string | null
  kickoff_at: string | null
  chronological_order: number | null
  home_team: string | null
  away_team: string | null
  home_score_ft: number | null
  away_score_ft: number | null
  home_score_ht: number | null
  away_score_ht: number | null
  model_key: string
  model_label: string
  model_short_label: string
  weights: Record<string, number>
  weights_version: string
  is_current_model: boolean
  current_model_key: string
  market_key: string | null
  target_market: string | null
  market_label: string | null
  signal_family: string | null
  period: string | null
  line: string | null
  model_active: boolean
  active_cell_count: number
  active_cells: HistoricalSignalCell[]
  active_signal_groups: string[]
  active_source_columns: string[]
  active_cell_labels: Array<string | null>
  consensus_model_count: number
  consensus_models: string[]
  active_in_current_model_F: boolean
  overlap_with_current_model_F: boolean
  prob_cecchino: number | null
  quota_cecchino: number | null
  rating: number | null
  edge: number | null
  vantaggio_probabilistico: number | null
  purchasability_score: number | null
  purchasability_band: string | null
  purchasability_status: string | null
  quote_quality: string | null
  is_real_book_quote: boolean | null
  is_derived_quote: boolean | null
  real_book_odds: number | null
  derived_odds: number | null
  won: boolean | null
  evaluation_status: string | null
  settlement_status: string | null
  result_reason: string | null
  profit_1u_real: number | null
  profit_1u_synthetic: number | null
  result_missing?: boolean
  market_join_status: string
  performance_eligible?: boolean
}

export type HistoricalSignalOverlapCell = {
  model_a: string
  model_b: string
  intersection_count: number
  union_count: number
  jaccard_pct: number | null
  overlap_a_pct: number | null
  overlap_b_pct: number | null
}

export type HistoricalSignalConsensusBucket = {
  market_key: string
  consensus_model_count: number
  opportunity_count: number
  wins: number
  losses: number
  hit_rate: number | null
  real_quote_count: number
  real_profit_1u: number | null
  real_roi_pct: number | null
  derived_quote_count: number
  synthetic_profit_1u: number | null
  synthetic_roi_pct: number | null
  unavailable_quote_count: number
}

export type HistoricalSignalExportReconciliation = {
  cell_rows: number
  opportunity_rows: number
  unique_opportunity_ids: number
  duplicate_opportunity_ids: number
  sum_active_cell_count: number
  cell_rows_equal_sum_active_cell_count: boolean
  opportunity_id_unique: boolean
  models_present: string[]
  current_model_key: string
  performance_uses_opportunities_only: boolean
  cell_rows_not_independent: boolean
}

export type HistoricalSignalMarketJoinDiagnostics = {
  opportunities_total: number
  matched_count: number
  missing_count: number
  ambiguous_count: number
  invalid_mapping_count: number
  matched_pct: number | null
  by_model_key?: Record<string, Record<string, number>>
  by_market_key?: Record<string, Record<string, number>>
}

export type HistoricalCurrentModelFDiagnostics = {
  current_model_key: string
  note?: string
  opportunities_total: number
  opportunities_shared_with_all_models: number
  opportunities_not_shared_with_all_models: number
  opportunities_unique_to_F: number
  opportunities_excluded_by_F_but_selected_by_other_models: number
  performance_by_market_key?: Record<string, Record<string, unknown>>
  overlap_per_model?: Array<Record<string, unknown>>
  consensus_distribution?: HistoricalSignalConsensusBucket[]
  active_cell_combinations_by_market?: Array<Record<string, unknown>>
  competition_distribution?: Array<{ competition_name: string; opportunity_count: number }>
  chronological_halves?: Record<string, unknown>
  f_selected_vs_excluded_same_market?: Array<Record<string, unknown>>
}

export type HistoricalRunSignalModelAnalytics = {
  model_key: string
  model_label: string
  model_short_label: string
  weights: Record<string, number>
  weights_version: string
  is_current_model: boolean
  /** Legacy: conteggio celle attive (non opportunità). */
  signals_activated: number
  matches_with_signal: number
  wins: number
  losses: number
  hit_rate: number | null
  real_quote_count: number
  real_profit: number | null
  real_roi: number | null
  derived_quote_count: number
  synthetic_profit: number | null
  synthetic_roi: number | null
  average_odds?: number | null
  max_losing_streak: number
  market_best: string | null
  market_worst: string | null
  competition_best: string | null
  competition_worst: string | null
  /** Opportunità uniche del modello. */
  opportunity_count?: number
  model_active_opportunity_count?: number
  /** Alias deprecato di model_active_opportunity_count (non overlap con F). */
  with_signal_active?: number
  model_active_match_count?: number
  matches_with_opportunity?: number
  model_active_market_count?: number
  markets_count?: number
  active_cell_row_count?: number
  average_active_cells_per_opportunity?: number | null
  average_active_cells?: number | null
  median_active_cells_per_opportunity?: number | null
  max_active_cells_per_opportunity?: number
  result_missing?: number
  overlap_with_current_model_F_count?: number
  overlap_with_current_model_F_pct?: number | null
  unique_vs_current_model_F_count?: number
  current_model_F_only_count?: number
  competitions_count?: number
  real_profit_1u?: number | null
  real_roi_pct?: number | null
  synthetic_profit_1u?: number | null
  synthetic_roi_pct?: number | null
  unavailable_quote_count?: number
}

/** Alias storico; campi estesi restano opzionali per compatibilità payload precedenti. */
export type HistoricalSignalModelSummary = HistoricalRunSignalModelAnalytics

export type HistoricalRunSignalsDashboard = {
  run_id: number
  models: HistoricalRunSignalModelAnalytics[]
  current_model_key: string
  note?: string
  analytics_aggregation_version?: string
  signal_export_schema_version?: string
  performance_granularity?: string
  opportunity_rows?: number
  cell_rows?: number
  concurrent_active_signals?: Record<string, number>
  model_overlap_matrix?: HistoricalSignalOverlapCell[]
  consensus_distribution?: HistoricalSignalConsensusBucket[]
  market_join_diagnostics?: HistoricalSignalMarketJoinDiagnostics | null
  signal_export_reconciliation?: HistoricalSignalExportReconciliation | null
  current_model_F_diagnostics?: HistoricalCurrentModelFDiagnostics | null
  cell_attribution?: Array<Record<string, unknown>>
  model_x_market?: Array<Record<string, unknown>>
  model_x_competition?: Array<Record<string, unknown>>
  model_x_consensus?: Array<Record<string, unknown>>
}

export type HistoricalRunBalanceAnalytics = {
  run_id: number
  pillars: Array<Record<string, unknown>>
  combinations: Array<Record<string, unknown>>
  note?: string
}

export type HistoricalRunGoalIntensityAnalytics = {
  run_id: number
  components: Array<Record<string, unknown>>
  combinations: Array<Record<string, unknown>>
  note?: string
}

export type HistoricalRunCompetitionAnalytics = {
  competition_name: string
  country?: string | null
  processed: number
  eligible: number
  excluded: number
  errors: number
  coverage_pct: number
  markets_generated: number
  real_quote_coverage: number
  derived_quote_coverage: number
  best_market_by_real_roi: string | null
  worst_market_by_real_roi: string | null
  real_profit_by_market: Record<string, number>
  real_roi_by_market: Record<string, number | null>
  exclusions_by_reason: Record<string, number>
  module_coverage: Record<string, HistoricalRunModuleCoverage>
}

export type HistoricalRunTimelinePoint = {
  period_key: string
  period_label: string
  historical_date_from: string | null
  historical_date_to: string | null
  processed: number
  eligible: number
  excluded: number
  hit_rate: number | null
  average_rating: number | null
  average_purchasability: number | null
  signals_count: number
  balance_coverage: number
  goal_intensity_coverage: number
  real_profit_by_market: Record<string, number>
  real_roi_by_market: Record<string, number | null>
}

export type HistoricalRunPattern = {
  pattern_id: string
  title?: string
  conditions: Record<string, unknown>
  market_key?: string | null
  sample_size: number
  wins: number
  losses: number
  hit_rate: number | null
  real_quote_count: number
  derived_quote_count?: number
  unavailable_quote_count?: number
  real_profit: number
  real_roi: number | null
  synthetic_profit: number
  synthetic_roi: number | null
  competitions_count: number
  main_competition?: string | null
  main_competition_share?: number | null
  stability?: Record<string, unknown> | null
  cross_competition_stability?: string | null
  status: string
  is_diagnostic?: boolean
  limitations: string[]
}

export type HistoricalRunExclusion = {
  reason_code: string
  label: string
  total: number
  percentage: number
  competitions: string[]
  chronological_distribution: Record<string, number>
  first_occurrence: string | null
  last_occurrence: string | null
  related_module: string
  is_expected: boolean
  is_data_quality_problem: boolean
}

export type HistoricalRunMatchRow = {
  snapshot_id: number
  lab_match_id: number
  date: string | null
  competition: string
  home_team: string | null
  away_team: string | null
  result: Record<string, unknown>
  eligibility: string
  exclusion_reason: string | null
  highest_rating_market: string | null
  highest_rating: number | null
  purchasability_summary: Record<string, unknown>
  active_signal_models: string[]
  balance_class: string
  goal_intensity_status: string
  quote_coverage: { real: number; derived: number; total: number }
  won_markets: string[]
  lost_markets: string[]
}

export type HistoricalRunMatchDetail = {
  run_id: number
  snapshot_id: number
  identity: Record<string, unknown>
  prematch: Record<string, unknown>
  result_after_lock: Record<string, unknown>
}

export function historicalRunFiltersToQuery(filters: HistoricalRunFilters): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  const q = params.toString()
  return q ? `?${q}` : ''
}

export function parseHistoricalRunFiltersFromSearch(search: string): HistoricalRunFilters {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  const out: HistoricalRunFilters = {}
  const keys: Array<keyof HistoricalRunFilters> = [
    'competition',
    'date_from',
    'date_to',
    'market_key',
    'rating_band',
    'purchasability_band',
    'quote_quality',
    'signal_model',
    'signal_active',
    'balance_class',
    'goal_intensity_status',
    'purchasability_status',
    'eligibility_status',
  ]
  for (const k of keys) {
    const v = params.get(k)
    if (v) out[k] = v
  }
  return out
}

function dashboardGet<T>(path: string, filters: HistoricalRunFilters): Promise<T> {
  return requestJson(`${path}${historicalRunFiltersToQuery(filters)}`)
}

export function getHistoricalRunDashboardOverview(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunDashboardOverview> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/overview`, filters)
}

export function getHistoricalRunDashboardMarkets(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ markets: HistoricalRunDashboardMarket[]; note?: string }> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/markets`, filters)
}

export function getHistoricalRunDashboardRatings(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{
  bands: string[]
  matrix: HistoricalRunRatingCell[]
  note?: string
  warning?: string
  analytics_aggregation_version?: string
}> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/ratings`, filters)
}

export function getHistoricalRunDashboardPurchasability(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunOfficialPurchasability> {
  return dashboardGet(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/purchasability`,
    filters,
  )
}

export type HistoricalPurchasabilityV3ReplayIssueExample = {
  code?: string
  message?: string
  snapshot_id?: number
  market_key?: string
  competition_name?: string
  score_replay_status?: string
  performance_evaluation_status?: string
  [key: string]: string | number | boolean | null | undefined
}

export type HistoricalPurchasabilityV3ReplayMarketCoverage = {
  eligible_rows: number
  exact_replay_ready: number
  ready_with_warning: number
  gate_only_ready: number
  not_replayable: number
  invalid_integrity?: number
  invalid_pre_match_integrity?: number
  ambiguous_market_join?: number
  classified_total?: number
  unclassified?: number
  quote_real: number
  quote_derived: number
  quote_unavailable: number
  quote_inconsistent?: number
  performance_real_ready: number
  performance_synthetic_ready: number
  performance_result_without_profit?: number
  performance_not_applicable?: number
}

export type HistoricalPurchasabilityV3ReplayFamilyCoverage = {
  snapshots_with_full_family: number
  snapshots_with_partial_family: number
  snapshots_with_missing_family: number
  exact_replay_ready: number
  ready_with_warning: number
  not_replayable: number
  family_decisions_theoretical: number
}

export type HistoricalPurchasabilityV3ReplayProbeMarket = {
  submitted?: number
  returned?: number
  scored?: number
  gate_failed?: number
  unavailable?: number
  not_applicable?: number
  unsupported?: number
  errors?: number
  unclassified?: number
}

export type HistoricalPurchasabilityV3ReplayProbe = {
  skipped?: boolean
  reason?: string
  probe_is_diagnostic_only?: boolean
  probe_not_a_backtest?: boolean
  probe_snapshot_limit?: number
  snapshots_selected?: number
  snapshots_probed?: number
  markets_expected?: number
  panel_rows_submitted?: number
  formula_items_returned?: number
  markets_scored?: number
  markets_gate_failed?: number
  markets_unavailable?: number
  markets_not_applicable?: number
  markets_unsupported?: number
  markets_error?: number
  markets_unclassified?: number
  snapshots_with_error?: number
  probe_classified_total?: number
  expected_vs_returned_status?: string
  by_market?: Record<string, HistoricalPurchasabilityV3ReplayProbeMarket>
  errors?: Array<Record<string, string | number | null | undefined>>
  [key: string]: unknown
}

export type HistoricalPurchasabilityV3ReplayPreflight = {
  schema_version: string
  integrity_policy_version?: string
  status: 'ready' | 'ready_with_warnings' | 'blocked' | string
  generated_at: string
  cache_hit?: boolean
  run: {
    run_id: number
    season_label: string
    status: string
    run_scope?: string | null
    is_partial_run?: boolean
    not_full_season_report?: boolean
    completed_at?: string | null
    source_git_commit?: string | null
    source_revision_status?: string | null
    scan_version?: string
  }
  formula: {
    candidate_version: string
    formula_version: string
    audit_version: string
    runtime_git_commit?: string | null
    runtime_git_commit_source?: string | null
    historical_profile_used: boolean
    fixed_scales_used: boolean
  }
  bookmakers: {
    historical: string
    today_operational: string
    providers_are_different: boolean
    bookmaker_parity_status?: string
    formula_provider_dependency?: string
  }
  source_integrity: {
    snapshots_total?: number
    snapshots_eligible_core?: number
    snapshots_excluded?: number
    exclusions_by_reason?: Record<string, number>
    with_payload_hash?: number
    with_historical_freeze_lock?: number
    with_pre_match_hash?: number
    with_pre_match_lock?: number
    lock_before_kickoff?: number
    invalid_lock_timestamp?: number
    historical_reconstruction_verified?: number
    historical_reconstruction_with_warning?: number
    historical_reconstruction_invalid?: number
    chronological_lock_check_applicable?: number
    chronological_lock_check_passed?: number
    chronological_lock_check_failed?: number
    chronological_lock_check_not_applicable?: number
    duplicate_market_keys?: number
    snapshots_with_duplicates?: number
    formula_input_whitelist_verified?: boolean
    post_match_fields_excluded?: boolean
    score_performance_phase_separation_verified?: boolean
    integrity_mode_dominant?: string | null
    integrity_policy_version?: string
  }
  workload: {
    supported_markets_per_snapshot: number
    theoretical_evaluations: number
    market_rows_found?: number
    exact_replay_ready: number
    ready_with_warning: number
    gate_only_ready: number
    not_replayable: number
    invalid_integrity?: number
    ambiguous_market_join?: number
    classified_evaluations_total?: number
    unclassified_evaluations?: number
    family_decisions_theoretical?: number
  }
  quote_quality: {
    real: number
    derived: number
    unavailable: number
    inconsistent_flags: number
  }
  fair_probability_checks?: Record<string, number>
  performance_coverage: {
    real_profit_ready: number
    synthetic_profit_ready: number
    result_available_but_profit_missing: number
    not_applicable: number
  }
  by_market: Record<string, HistoricalPurchasabilityV3ReplayMarketCoverage>
  by_family?: Record<string, HistoricalPurchasabilityV3ReplayFamilyCoverage>
  by_competition?: Record<string, Record<string, number>>
  adapter_contract?: Record<string, unknown>
  anti_leakage?: {
    pre_match_input_fields?: string[]
    post_match_performance_fields?: string[]
    forbidden_formula_fields?: string[]
    formula_payload_allowed_fields?: string[]
    formula_payload_forbidden_fields_found?: string[]
    performance_fields_loaded_but_not_forwarded?: boolean
    anti_leakage_status?: string
    result_fields_passed_to_formula?: boolean
    settlement_fields_passed_to_formula?: boolean
  }
  probe?: HistoricalPurchasabilityV3ReplayProbe
  blockers: Array<{ code: string; message: string }>
  warnings: Array<{ code: string; message: string }>
  issue_examples?: Record<string, HistoricalPurchasabilityV3ReplayIssueExample[]>
  problematic_snapshots?: Array<Record<string, unknown>>
  replay_recommendation: {
    can_replay_without_full_scan: boolean
    requires_new_external_data: boolean
    requires_model_recalculation: boolean
    requires_database_migration: boolean
    recommended_next_action: string
  }
  status_rules?: Record<string, unknown>
  resource_profile?: {
    strategy?: string
    full_orm_entities_loaded?: boolean
    snapshot_json_fields_loaded?: boolean
    market_json_fields_loaded?: boolean
    market_rows_streamed?: number
    max_market_rows_held_in_memory?: number
    stream_yield_per?: number
    probe_requested?: boolean
    probe_snapshot_count?: number
    duration_ms?: number
    resource_budget_exceeded?: boolean
  }
  query_profile?: Record<string, number>
}

export function getHistoricalPurchasabilityV3ReplayPreflight(
  runId: number,
  opts?: { includeProbe?: boolean },
): Promise<HistoricalPurchasabilityV3ReplayPreflight> {
  const params = new URLSearchParams()
  if (opts?.includeProbe) params.set('include_probe', 'true')
  const q = params.toString()
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/purchasability-v3-replay/preflight${q ? `?${q}` : ''}`,
  )
}

export const PURCHASABILITY_V3_FORMULA_VERSION =
  'cecchino_purchasability_v3_fixed_discount_v1'
export const PURCHASABILITY_V3_PREFLIGHT_SCHEMA_VERSION =
  'cecchino_lab_purchasability_v3_replay_preflight_v2'
export const PURCHASABILITY_V3_INTEGRITY_POLICY_VERSION =
  'cecchino_lab_historical_reconstruction_integrity_v1'
export const PURCHASABILITY_V3_REPLAY_POLL_MS = 2500

export type PurchasabilityV3ReplayStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'cancel_requested'
  | 'cancelled'
  | 'failed'
  | 'interrupted'

export type PurchasabilityV3ReplayRun = {
  id: number
  source_scan_run_id: number
  status: PurchasabilityV3ReplayStatus | string
  effective_status?: PurchasabilityV3ReplayStatus | string
  replay_schema_version?: string
  replay_engine_version?: string
  candidate_version?: string
  formula_version?: string
  audit_version?: string
  preflight_schema_version?: string
  integrity_policy_version?: string
  requested_at?: string | null
  started_at?: string | null
  heartbeat_at?: string | null
  completed_at?: string | null
  snapshots_total?: number
  snapshots_processed?: number
  evaluations_total?: number
  evaluations_processed?: number
  results_persisted?: number
  progress_pct?: number | null
  current_snapshot_id?: number | null
  current_chronological_order?: number | null
  current_competition?: string | null
  scored_count?: number
  gate_failed_count?: number
  unavailable_count?: number
  not_applicable_count?: number
  error_count?: number
  unclassified_count?: number
  exact_source_count?: number
  warning_source_count?: number
  non_replayable_source_count?: number
  real_quote_count?: number
  derived_quote_count?: number
  unavailable_quote_count?: number
  cancel_requested?: boolean
  resume_count?: number
  attempt_count?: number
  idempotency_key?: string
  summary?: Record<string, unknown> | null
  error?: {
    error?: string
    message?: string
    details?: unknown
    phase?: string
    recoverable?: boolean
  } | null
  can_cancel?: boolean
  can_resume?: boolean
  reused_existing?: boolean
}

export function isPurchasabilityV3ReplayActive(status: string): boolean {
  return status === 'queued' || status === 'running' || status === 'cancel_requested'
}

export function startPurchasabilityV3Replay(
  runId: number,
  body: {
    confirmed: true
    expected_formula_version: string
    expected_preflight_schema_version: string
    expected_integrity_policy_version: string
  },
): Promise<PurchasabilityV3ReplayRun> {
  return postJson(
    `/api/admin/cecchino-lab/historical-scans/${runId}/purchasability-v3-replays`,
    body,
  )
}

export function getPurchasabilityV3Replay(replayId: number): Promise<PurchasabilityV3ReplayRun> {
  return requestJson(`/api/cecchino-lab/purchasability-v3-replays/${replayId}`)
}

export function listPurchasabilityV3Replays(
  runId: number,
): Promise<{ items: PurchasabilityV3ReplayRun[] }> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}/purchasability-v3-replays`)
}

export function cancelPurchasabilityV3Replay(
  replayId: number,
): Promise<PurchasabilityV3ReplayRun> {
  return postJson(`/api/admin/cecchino-lab/purchasability-v3-replays/${replayId}/cancel`)
}

export function resumePurchasabilityV3Replay(
  replayId: number,
): Promise<PurchasabilityV3ReplayRun> {
  return postJson(`/api/admin/cecchino-lab/purchasability-v3-replays/${replayId}/resume`)
}

export const PURCHASABILITY_V31_FORMULA_VERSION =
  'cecchino_purchasability_v31_fixed_discount_empirical_v2'
export const PURCHASABILITY_V31_PREFLIGHT_SCHEMA_VERSION =
  'cecchino_lab_purchasability_v31_replay_preflight_v2'
export const PURCHASABILITY_V31_INTEGRITY_POLICY_VERSION =
  'cecchino_lab_historical_reconstruction_integrity_v1'

export type PurchasabilityFormulaId = 'v3' | 'v31'

export function getHistoricalPurchasabilityReplayPreflight(
  runId: number,
  opts?: { includeProbe?: boolean; formulaVersion?: PurchasabilityFormulaId },
): Promise<HistoricalPurchasabilityV3ReplayPreflight> {
  const formula = opts?.formulaVersion || 'v3'
  if (formula === 'v3') {
    return getHistoricalPurchasabilityV3ReplayPreflight(runId, {
      includeProbe: opts?.includeProbe,
    })
  }
  const params = new URLSearchParams()
  params.set('formula_version', 'v31')
  if (opts?.includeProbe) params.set('include_probe', 'true')
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/purchasability-replay/preflight?${params}`,
  )
}

export function startPurchasabilityReplay(
  runId: number,
  body: {
    confirmed: true
    formula_version: PurchasabilityFormulaId
    expected_formula_version: string
    expected_preflight_schema_version: string
    expected_integrity_policy_version: string
  },
): Promise<PurchasabilityV3ReplayRun> {
  if (body.formula_version === 'v3') {
    return startPurchasabilityV3Replay(runId, {
      confirmed: true,
      expected_formula_version: body.expected_formula_version,
      expected_preflight_schema_version: body.expected_preflight_schema_version,
      expected_integrity_policy_version: body.expected_integrity_policy_version,
    })
  }
  return postJson(`/api/admin/cecchino-lab/historical-scans/${runId}/purchasability-replays`, body)
}

export function getPurchasabilityReplayAnalytics(
  replayId: number,
  formulaVersion: PurchasabilityFormulaId = 'v3',
): Promise<HistoricalPurchasabilityV3ReplayAnalytics & Record<string, unknown>> {
  if (formulaVersion === 'v3') {
    return getPurchasabilityV3ReplayAnalytics(replayId)
  }
  return requestJson(
    `/api/cecchino-lab/purchasability-replays/${replayId}/analytics?formula_version=v31`,
  )
}

export function getPurchasabilityV31Decision(
  replayId: number,
): Promise<Record<string, unknown>> {
  return requestJson(`/api/cecchino-lab/purchasability-replays/${replayId}/decision`)
}

export function getPurchasabilityOperationalConfig(): Promise<{
  operational_version: string
  fallback_version: string
  strong_buy_message_allowed?: boolean
  v31_is_operational?: boolean
  shadow_default?: boolean
}> {
  return requestJson('/api/cecchino-lab/purchasability/operational')
}

export function promotePurchasabilityV31(
  replayId: number,
  body: {
    confirm_token: string
    expected_formula_version: string
    idempotency_key?: string
  },
): Promise<Record<string, unknown>> {
  return postJson(
    `/api/admin/cecchino-lab/purchasability-replays/${replayId}/promote`,
    body,
  )
}

export type HistoricalPurchasabilityV3ReplayPerformanceBucket = {
  stake_count: number
  profit_units: number | null
  roi_pct: number | null
  wins?: number
  losses?: number
  hit_rate_pct?: number | null
  average_odds?: number | null
  technical_aggregate_only?: boolean
  do_not_interpret_as_strategy?: boolean
  diagnostic_only?: boolean
  exclude_from_real_roi?: boolean
  not_a_real_bet365_quote?: boolean
}

export type HistoricalPurchasabilityV3ReplayReconciliation = {
  status: 'ok' | 'failed' | string
  all_evaluations?: number
  buckets?: Record<string, number>
  quote_buckets?: {
    real?: number
    derived?: number
    unavailable?: number
  }
  checks?: Array<{ code: string; ok: boolean; detail?: unknown }>
}

export type HistoricalPurchasabilityV3ReplayMarketAnalytics = {
  evaluations_total: number
  scored: number
  gate_failed: number
  unavailable: number
  real_quote?: number
  derived_quote?: number
  quote_type?: string
  performance_real?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  performance_synthetic?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  not_a_real_bet365_quote?: boolean
  exclude_from_real_roi?: boolean
}

export type HistoricalPurchasabilityV3ReplayPenaltyAnalytics = {
  descriptive_observational_analysis?: boolean
  fields?: Record<
    string,
    {
      count_available?: number
      count_applied?: number
      application_rate?: number | null
      mean?: number | null
      median?: number | null
    }
  >
  total_penalty_bands?: Record<string, number>
}

export type HistoricalPurchasabilityV3ReplayAnalytics = {
  schema_version: string
  status: 'ready' | 'ready_with_warnings' | 'blocked' | string
  generated_at?: string
  replay?: {
    replay_id?: number
    source_scan_run_id?: number
    status?: string
    formula_version?: string
    replay_schema_version?: string
  }
  universes?: {
    ALL_EVALUATIONS?: number
    SCORED_EVALUATIONS?: number
    GATE_FAILED_EVALUATIONS?: number
    UNAVAILABLE_EVALUATIONS?: number
    REAL_PERFORMANCE_UNIVERSE?: number
    SYNTHETIC_PERFORMANCE_UNIVERSE?: number
  }
  reconciliation?: HistoricalPurchasabilityV3ReplayReconciliation
  performance_real?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  performance_synthetic?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  by_market?: Record<string, HistoricalPurchasabilityV3ReplayMarketAnalytics>
  penalties?: HistoricalPurchasabilityV3ReplayPenaltyAnalytics
  warnings?: string[]
  blockers?: Array<{ code: string; message: string }>
  metadata?: {
    formula_recomputed?: boolean
    analytics_reads_persisted_replay?: boolean
    source_replay_id?: number
    source_replay_immutable?: boolean
    report_valid?: boolean
  }
  resource_profile?: {
    strategy?: string
    rows_read?: number
    formula_recomputed?: boolean
    duration_ms?: number
  }
}

export type PurchasabilityV3ReplayReportMode = 'analysis' | 'full_archive'

/** Metadati ufficiali Acquistabilità V3 (dashboard / sezione Run). */
export type HistoricalRunOfficialPurchasabilityMetadata = {
  official_version: 'V3'
  official_purchasability_version?: 'V3' | string
  source_type: 'historical_replay'
  official_purchasability_source?: 'replay_v3' | string
  replay_id: number | null
  replay_status?: string | null
  formula_version?: string | null
  replay_engine_version?: string | null
  replay_schema_version?: string | null
  candidate_version?: string | null
  analytics_schema_version?: string | null
  export_schema_version?: string | null
  legacy_purchasability_read?: false
  legacy_fallback_allowed?: boolean
  legacy_fallback_used: false
  formula_recomputed?: false | boolean
  analytics?: HistoricalPurchasabilityV3ReplayAnalytics | null
  analytics_metadata?: Record<string, unknown> | null
}

export type HistoricalRunOfficialPurchasabilityCta = {
  label: string
  path: string
}

/** Payload ufficiale dashboard Acquistabilità V3 (ready o unavailable). */
export type HistoricalRunOfficialPurchasability = HistoricalRunOfficialPurchasabilityMetadata & {
  status: 'ready' | 'ready_with_warnings' | 'blocked' | 'unavailable' | string
  run_id?: number
  source_scan_run_id?: number
  filters?: HistoricalRunFilters | Record<string, unknown>
  message?: string
  reason?: string
  cta?: HistoricalRunOfficialPurchasabilityCta
  results_persisted?: number
  evaluations_total?: number
  scored?: number
  gate_failed?: number
  unavailable?: number
  real_quote_count?: number
  derived_quote_count?: number
  reconciliation?: HistoricalPurchasabilityV3ReplayReconciliation
  reconciliation_status?: string | null
  universes?: HistoricalPurchasabilityV3ReplayAnalytics['universes']
  score_distribution?: unknown
  gate_analysis?: unknown
  performance_real?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  performance_synthetic?: HistoricalPurchasabilityV3ReplayPerformanceBucket
  by_market?: Record<string, Record<string, unknown>>
  family_decisions?: unknown
}

/** Endpoint run-centric: analytics V3 ufficiale (409 se replay assente). */
export function getHistoricalRunOfficialPurchasability(
  runId: number,
): Promise<HistoricalPurchasabilityV3ReplayAnalytics> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}/purchasability`)
}

export async function downloadHistoricalRunOfficialPurchasabilityReport(
  runId: number,
  mode: PurchasabilityV3ReplayReportMode = 'analysis',
): Promise<void> {
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', mode)
  const res = await fetch(
    `${base}/api/cecchino-lab/historical-scans/${runId}/purchasability/report?${params.toString()}`,
  )
  if (!res.ok) {
    const message = await readHttpErrorMessage(
      res,
      `Download report Acquistabilità V3 fallito (${res.status})`,
    )
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const filename = match?.[1] || `cecchino-run-${runId}-purchasability-v3.zip`
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function getPurchasabilityV3ReplayAnalytics(
  replayId: number,
): Promise<HistoricalPurchasabilityV3ReplayAnalytics> {
  return requestJson(`/api/cecchino-lab/purchasability-v3-replays/${replayId}/analytics`)
}

export async function downloadPurchasabilityV3ReplayReport(
  replayId: number,
  mode: PurchasabilityV3ReplayReportMode = 'analysis',
): Promise<void> {
  const base = getApiBase()
  const params = new URLSearchParams()
  params.set('mode', mode)
  const res = await fetch(
    `${base}/api/cecchino-lab/purchasability-v3-replays/${replayId}/report?${params.toString()}`,
  )
  if (!res.ok) {
    let message = `Download report V3 fallito (${res.status})`
    try {
      const body = (await res.json()) as { detail?: string; message?: string }
      message = body?.detail || body?.message || message
    } catch {
      /* ignore */
    }
    if (res.status === 409) {
      message =
        'Il replay deve essere completato prima di generare analytics o report.'
    }
    throw new AdminHttpError(res.status, message, null)
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const match = /filename="([^"]+)"/.exec(cd)
  const fallback =
    mode === 'full_archive'
      ? `cecchino-purchasability-v3-replay-${replayId}-full.zip`
      : `cecchino-purchasability-v3-replay-${replayId}-analysis.zip`
  const filename = match?.[1] || fallback
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function getHistoricalRunDashboardSignals(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunSignalsDashboard> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/signals`, filters)
}

export function getHistoricalRunDashboardBalance(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunBalanceAnalytics> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/balance`, filters)
}

export function getHistoricalRunDashboardGoalIntensity(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<HistoricalRunGoalIntensityAnalytics> {
  return dashboardGet(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/goal-intensity`,
    filters,
  )
}

export function getHistoricalRunDashboardCompetitions(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ competitions: HistoricalRunCompetitionAnalytics[]; note?: string }> {
  return dashboardGet(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/competitions`,
    filters,
  )
}

export function getHistoricalRunDashboardTimeline(
  runId: number,
  filters: HistoricalRunFilters = {},
  opts?: { granularity?: string; block_size?: number },
): Promise<{ points: HistoricalRunTimelinePoint[]; granularity: string; note?: string }> {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  if (opts?.granularity) params.set('granularity', opts.granularity)
  if (opts?.block_size != null) params.set('block_size', String(opts.block_size))
  const q = params.toString()
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/dashboard/timeline${q ? `?${q}` : ''}`,
  )
}

export function getHistoricalRunDashboardPatterns(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{
  positive: HistoricalRunPattern[]
  negative: HistoricalRunPattern[]
  watchlist: HistoricalRunPattern[]
  unstable: HistoricalRunPattern[]
  diagnostics?: HistoricalRunPattern[]
  analytics_aggregation_version?: string
  note?: string
}> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/patterns`, filters)
}

export function getHistoricalRunDashboardExclusions(
  runId: number,
  filters: HistoricalRunFilters = {},
): Promise<{ items: HistoricalRunExclusion[]; total_excluded: number; note?: string }> {
  return dashboardGet(`/api/cecchino-lab/historical-scans/${runId}/dashboard/exclusions`, filters)
}

export function listHistoricalRunMatches(
  runId: number,
  filters: HistoricalRunFilters = {},
  opts?: { limit?: number; offset?: number; sort_by?: string; sort_order?: string },
): Promise<{
  items: HistoricalRunMatchRow[]
  total: number
  limit: number
  offset: number
}> {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  if (!params.has('eligibility_status')) params.set('eligibility_status', 'all')
  params.set('limit', String(opts?.limit ?? 50))
  params.set('offset', String(opts?.offset ?? 0))
  if (opts?.sort_by) params.set('sort_by', opts.sort_by)
  if (opts?.sort_order) params.set('sort_order', opts.sort_order)
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/matches?${params.toString()}`,
  )
}

export function getHistoricalRunMatchDetail(
  runId: number,
  snapshotId: number,
): Promise<HistoricalRunMatchDetail> {
  return requestJson(`/api/cecchino-lab/historical-scans/${runId}/matches/${snapshotId}`)
}

/* ─── Historical KPI Signals (STEP 4A/4B) ─── */

export type HistoricalKpiSignalsFilters = {
  competition?: string
  date_from?: string
  date_to?: string
  rating_bucket?: string
  selection_key?: string
  evaluation_status?: string
  quote_type?: 'real' | 'derived' | 'all'
  purchasability_min_score?: number | null
}

export type PurchasabilityFilterImpact = {
  enabled: boolean
  min_score: number | null
  official_replay_id: number | null
  formula_version: string | null
  base_signals_before_filter: number
  v3_supported_and_joined: number
  v3_scored: number
  matched_threshold: number
  excluded_unsupported_market: number
  excluded_missing_join: number
  excluded_gate_failed: number
  excluded_unavailable: number
  coverage_pct: number
  reason?: string
}

export type HistoricalKpiSignalsOverall = {
  signals_count: number
  evaluated_count: number
  wins: number
  losses: number
  pending_or_unsettled: number
  void_or_zero_profit: number
  win_rate_pct: number | null
  average_odds_played: number | null
  average_odds_won: number | null
  average_odds_void: number | null
  stake_count: number
  profit_units: number | null
  roi_pct: number | null
}

export type HistoricalKpiRatingBucket = HistoricalKpiSignalsOverall & {
  rating_bucket: string
  quote_type: string
  status: string
}

export type HistoricalKpiHeatmapCell = HistoricalKpiSignalsOverall & {
  rating_bucket: string
  selection_key: string
  quote_type: string
  sample_class: string
  average_odds?: number | null
}

export type HistoricalKpiSignalsSummary = {
  schema_version: string
  generated_at: string
  run: {
    run_id: number
    season_label: string
    status: string
    scope: string
    is_partial_run?: boolean
  }
  filters: HistoricalKpiSignalsFilters
  available_filters: {
    competitions: string[]
    selection_keys: string[]
    date_min: string | null
    date_max: string | null
  }
  overall: {
    real: HistoricalKpiSignalsOverall | null
    synthetic: HistoricalKpiSignalsOverall | null
  }
  by_rating_bucket: HistoricalKpiRatingBucket[]
  heatmap: {
    rating_buckets: string[]
    selection_keys: string[]
    cells: HistoricalKpiHeatmapCell[]
  }
  diagnostics: {
    rows_scanned: number
    rating_null: number
    rating_below_50: number
    eligible_rows: number
    performance_real_ready: number
    performance_synthetic_ready: number
  }
  resource_profile: {
    strategy: string
    query_count: number
    rows_materialized: number
    full_orm_entities_loaded: boolean
    jsonb_payloads_loaded: boolean
  }
  purchasability_filter?: PurchasabilityFilterImpact
  reason?: string
  message?: string
}

export type HistoricalKpiTimelinePoint = {
  group_key: string
  group_label: string
  date_from: string | null
  date_to: string | null
  signals_count?: number
  evaluated_count?: number
  wins?: number
  losses?: number
  win_rate_pct?: number | null
  profit_units?: number | null
  roi_pct?: number | null
  stake_count?: number
  cumulative_profit_units?:
    | number
    | null
    | { real: number | null; synthetic: number | null }
  cumulative_roi_pct?: number | null | { real: number | null; synthetic: number | null }
  real?: HistoricalKpiSignalsOverall
  synthetic?: HistoricalKpiSignalsOverall
  by_rating_bucket?: Array<
    HistoricalKpiSignalsOverall & { rating_bucket: string; quote_type: string }
  >
}

export type HistoricalKpiTimelineResponse = {
  schema_version: string
  generated_at: string
  run: HistoricalKpiSignalsSummary['run']
  filters: HistoricalKpiSignalsFilters
  group_by: string
  effective_group_by: string
  grouping_fallback: string | null
  points: HistoricalKpiTimelinePoint[]
  resource_profile: HistoricalKpiSignalsSummary['resource_profile']
  purchasability_filter?: PurchasabilityFilterImpact
  reason?: string
  message?: string
}

export type HistoricalKpiActivationRow = {
  source_snapshot_id: number
  lab_match_id: number
  competition_name: string | null
  kickoff_at: string | null
  matchday_label: string | null
  home_team: string | null
  away_team: string | null
  market_key: string
  market_label: string
  rating: number | null
  rating_bucket: string | null
  quote_type: string
  quota_book: number | null
  won: boolean | null
  profit_units: number | null
  evaluation_status: string | null
  result_reason: string | null
  purchasability_score?: number | null
  purchasability_class?: string | null
  purchasability_gate_status?: string | null
  purchasability_formula_version?: string | null
  purchasability_supported?: boolean
  purchasability_exclusion_reason?: string | null
}

export type HistoricalKpiActivationsResponse = {
  items: HistoricalKpiActivationRow[]
  total: number
  limit: number
  offset: number
  filters: HistoricalKpiSignalsFilters
  resource_profile: HistoricalKpiSignalsSummary['resource_profile'] & {
    activations_page_size?: number
  }
  purchasability_filter?: PurchasabilityFilterImpact
  reason?: string
  message?: string
}

export function historicalKpiSignalsFiltersToQuery(
  filters: HistoricalKpiSignalsFilters,
  extra?: Record<string, string | number | undefined>,
): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v != null && String(v).trim() !== '') params.set(k, String(v))
    }
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function getHistoricalKpiSignalsSummary(
  runId: number,
  filters: HistoricalKpiSignalsFilters = {},
  init?: RequestInit,
): Promise<HistoricalKpiSignalsSummary> {
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/kpi-signals/summary${historicalKpiSignalsFiltersToQuery(filters)}`,
    init,
  )
}

export function getHistoricalKpiSignalsTimeline(
  runId: number,
  filters: HistoricalKpiSignalsFilters = {},
  groupBy: string = 'date',
  init?: RequestInit,
): Promise<HistoricalKpiTimelineResponse> {
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/kpi-signals/timeline${historicalKpiSignalsFiltersToQuery(
      filters,
      { group_by: groupBy },
    )}`,
    init,
  )
}

export function getHistoricalKpiSignalActivations(
  runId: number,
  filters: HistoricalKpiSignalsFilters = {},
  opts?: { limit?: number; offset?: number },
  init?: RequestInit,
): Promise<HistoricalKpiActivationsResponse> {
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/kpi-signals/activations${historicalKpiSignalsFiltersToQuery(
      filters,
      {
        limit: opts?.limit ?? 50,
        offset: opts?.offset ?? 0,
      },
    )}`,
    init,
  )
}

/* ─── Historical Signals A–F (STEP 4B) ─── */

export type HistoricalSignalsAfFilters = {
  competition?: string
  date_from?: string
  date_to?: string
  model_key?: string
  market_key?: string
  quote_type?: 'real' | 'derived' | 'all'
  minimum_consensus_models?: number
  only_current_model_F?: boolean
}

export type HistoricalSignalsAfModel = {
  model_key: string
  model_short_label?: string
  model_label?: string
  is_current_model?: boolean
  opportunity_count?: number
  model_active_opportunity_count?: number
  matches_with_signal?: number
  active_cell_row_count?: number
  signals_activated?: number
  average_active_cells_per_opportunity?: number | null
  average_active_cells?: number | null
  hit_rate?: number | null
  real_roi?: number | null
  real_roi_pct?: number | null
  synthetic_roi?: number | null
  synthetic_roi_pct?: number | null
  real_profit?: number | null
  synthetic_profit?: number | null
  overlap_with_current_model_F_count?: number | null
  overlap_with_current_model_F_pct?: number | null
  unique_vs_current_model_F_count?: number | null
  market_best?: string | null
  market_worst?: string | null
  [key: string]: string | number | boolean | null | undefined | Record<string, unknown>
}

export type HistoricalSignalsAfMarket = {
  model_key: string
  market_key: string
  real_roi_pct?: number | null
  synthetic_roi_pct?: number | null
  real_quote_count?: number
  derived_quote_count?: number
  sample_size?: number
  [key: string]: string | number | boolean | null | undefined
}

export type HistoricalSignalsAfSummary = {
  schema_version: string
  signal_export_schema_version: string
  generated_at: string
  run: {
    run_id: number
    season_label: string | null
    status: string | null
    scope: string
    is_partial_run?: boolean | null
  }
  filters: HistoricalSignalsAfFilters
  current_model_key: string
  performance_granularity: string
  models: HistoricalSignalsAfModel[]
  by_market: HistoricalSignalsAfMarket[]
  model_overlap_matrix: Array<{
    model_a: string
    model_b: string
    intersection_count: number
    union_count: number
    jaccard_pct: number | null
    overlap_a_pct: number | null
    overlap_b_pct: number | null
  }>
  consensus_distribution: Array<Record<string, unknown>>
  signal_export_reconciliation?: Record<string, unknown>
  current_model_F_diagnostics?: Record<string, unknown>
  unique_opportunities: number
  active_cells: number
  filtered_opportunity_count: number
  quote_buckets: { real: number; derived: number; note?: string }
  concurrent_active_signals: Record<string, number>
  note: string
  resource_profile: {
    strategy: string
    query_count: number
    snapshots_loaded: number
    opportunities_materialized: number
    full_orm_entities_loaded: boolean
    full_signals_json_returned: boolean
  }
}

export type HistoricalSignalsAfActivation = {
  opportunity_id: string
  snapshot_id: number
  lab_match_id: number
  competition_name: string | null
  kickoff_at: string | null
  home_team: string | null
  away_team: string | null
  model_key: string
  market_key: string | null
  market_label: string | null
  active_cell_count: number
  active_cells: Array<Record<string, unknown>>
  consensus_model_count: number | null
  consensus_models: string[] | null
  quota_book: number | null
  is_real_book_quote: boolean | null
  is_derived_quote: boolean | null
  quote_type: string | null
  won: boolean | null
  profit_1u_real: number | null
  profit_1u_synthetic: number | null
  evaluation_status: string | null
  rating: number | null
}

export type HistoricalSignalsAfActivationsResponse = {
  items: HistoricalSignalsAfActivation[]
  total: number
  limit: number
  offset: number
  filters: HistoricalSignalsAfFilters
  performance_granularity: string
  note: string
  resource_profile: HistoricalSignalsAfSummary['resource_profile'] & {
    activations_page_size?: number
  }
}

export function historicalSignalsAfFiltersToQuery(
  filters: HistoricalSignalsAfFilters,
  extra?: Record<string, string | number | boolean | undefined>,
): string {
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(filters)) {
    if (v != null && String(v).trim() !== '') params.set(k, String(v))
  }
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v != null && String(v).trim() !== '') params.set(k, String(v))
    }
  }
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function getHistoricalSignalsAfSummary(
  runId: number,
  filters: HistoricalSignalsAfFilters = {},
  init?: RequestInit,
): Promise<HistoricalSignalsAfSummary> {
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/signals-af/summary${historicalSignalsAfFiltersToQuery(filters)}`,
    init,
  )
}

export function getHistoricalSignalsAfActivations(
  runId: number,
  filters: HistoricalSignalsAfFilters = {},
  opts?: { limit?: number; offset?: number },
  init?: RequestInit,
): Promise<HistoricalSignalsAfActivationsResponse> {
  return requestJson(
    `/api/cecchino-lab/historical-scans/${runId}/signals-af/activations${historicalSignalsAfFiltersToQuery(
      filters,
      {
        limit: opts?.limit ?? 50,
        offset: opts?.offset ?? 0,
      },
    )}`,
    init,
  )
}

export const HISTORICAL_RUN_REPORT_MENU: Array<{
  mode: HistoricalReportMode
  module?: HistoricalReportModule
  label: string
  description?: string
  recommended?: boolean
  needsCompetition?: boolean
  sizeWarning?: boolean
}> = [
  { mode: 'ai_summary', label: 'Sintesi per ChatGPT', recommended: true },
  { mode: 'competition', label: 'Dettaglio per campionato', needsCompetition: true },
  { mode: 'module', module: 'signals', label: 'Dettaglio Segnali A–F' },
  { mode: 'module', module: 'balance', label: 'Dettaglio Balance / Equilibrio' },
  { mode: 'module', module: 'goal_intensity', label: 'Dettaglio Intensità Goal' },
  {
    mode: 'module',
    module: 'purchasability',
    label: 'Dettaglio Acquistabilità',
    description: 'Acquistabilità V3 ricostruita dal replay storico completato.',
  },
  { mode: 'module', module: 'markets', label: 'Dettaglio mercati' },
  {
    mode: 'full_archive',
    label: 'Archivio tecnico completo',
    sizeWarning: true,
  },
]

// ---------------------------------------------------------------------------
// Goal Intensity V4 vs V5 historical benchmark
// ---------------------------------------------------------------------------

export const GI_HISTORICAL_BENCHMARK_BUNDLE_VERSION =
  'cecchino_goal_intensity_v5_candidate_bundle_v2_1'
export const GI_HISTORICAL_BENCHMARK_PILOT_CONFIRM =
  'RUN_GOAL_INTENSITY_HISTORICAL_BENCHMARK_PILOT'
export const GI_HISTORICAL_BENCHMARK_FULL_CONFIRM =
  'RUN_GOAL_INTENSITY_HISTORICAL_BENCHMARK_FULL'
export const GI_HISTORICAL_BENCHMARK_POLL_MS = 2500
export const GI_HISTORICAL_BENCHMARK_DEFAULT_PILOT_SIZE = 300
export const GI_HISTORICAL_BENCHMARK_DEFAULT_SEED = 42

export type GiHistoricalBenchmarkJobStatus =
  | 'preview'
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancel_requested'
  | 'cancelled'

export type GiHistoricalBenchmarkPreflight = {
  status: string
  run: {
    id: number
    status: string
    season?: string | null
    snapshots_found?: number
    source_git_commit?: string | null
  }
  bundle: {
    id: number
    version: string
    status: string
    is_active: boolean
    definition_hash?: string | null
    intended_use?: string | null
  }
  independence: {
    status?: string
    scientific_label?: string
    overlap_count?: number
    overlap_pct?: number
    details?: Record<string, unknown>
  }
  availability: {
    v4_rebuildable?: number
    v4_persisted_available?: number
    v4_reconstructed_available?: number
    v4_total_available?: number
    v4_reconstruction_input_mismatch?: number
    v4_reconstruction_kpi_mismatch?: number
    v4_missing_context_data?: number
    v5_features_rebuildable?: number
    v5_rebuildable?: number
    five_models_rebuildable?: number
    paired_complete_estimate?: number
    paired_coverage_pct?: number
    pilot_paired_estimate?: number
    blocked?: boolean
    missing_by_reason?: Record<string, number>
    scoring_probe_n?: number
    scoring_probe_ok?: number
    five_models_probe_n?: number
    five_models_probe_ok?: number
  }
  pilot: {
    requested?: number
    selected?: number
    selection_hash?: string
    selection_protocol?: string
    competition_distribution?: Record<string, number>
    month_distribution?: Record<string, number>
    kickoff_range?: { min?: string | null; max?: string | null }
    random_seed?: number
  }
  checks: {
    external_api_calls?: number
    full_scan_required?: boolean
    base_run_writes?: number
    bundle_refit?: boolean
    result_used_in_prediction?: boolean
    full_scan_restarted?: boolean
    leakage_detected?: boolean
  }
  v4_persisted_available?: number
  v4_reconstructed_available?: number
  v4_reconstruction_input_mismatch?: number
  v4_reconstruction_kpi_mismatch?: number
  v4_missing_context_data?: number
  v4_total_available?: number
  v5_rebuildable?: number
  paired_complete_estimate?: number
  paired_coverage_pct?: number
  pilot_paired_estimate?: number
  five_models_probe_n?: number
  five_models_probe_ok?: number
  pilot_data_gate_status?: 'ok' | 'warning' | 'blocked' | string
  pilot_allowed?: boolean
  full_allowed_after_pilot?: boolean
  blocking_reasons?: string[]
  warnings?: string[]
  job_version?: string
  models?: string[]
  v4_provenance_manifest?: Record<string, unknown>
}

export type GiHistoricalBenchmarkJob = {
  job_id?: number
  id: number
  historical_run_id: number
  bundle_id: number
  job_version: string
  mode: 'pilot' | 'full' | string
  status: GiHistoricalBenchmarkJobStatus | string
  effective_status?: string
  is_stale?: boolean
  can_resume?: boolean
  independence_status?: string | null
  progress_pct?: number | null
  processed_snapshots?: number
  selected_snapshots?: number
  paired_complete?: number
  skipped?: number
  errors?: number
  cancel_requested?: boolean
  summary_json?: Record<string, unknown> | null
  missing_by_reason_json?: Record<string, number> | null
  params_json?: Record<string, unknown> | null
  preflight_json?: GiHistoricalBenchmarkPreflight | null
  selection_hash?: string
  started_at?: string | null
  last_checkpoint_at?: string | null
  completed_at?: string | null
  error_json?: Record<string, unknown> | null
  pilot_gate?: { ok: boolean; reasons: string[] } | null
  stale_checkpoint_seconds?: number
}

export function goalIntensityBenchmarkPreflight(
  runId: number,
  body?: {
    bundle_version?: string
    pilot_size?: number
    random_seed?: number
  },
): Promise<GiHistoricalBenchmarkPreflight> {
  return postJson(
    `/api/admin/cecchino-lab/historical/runs/${runId}/goal-intensity-benchmark/preflight`,
    {
      bundle_version: body?.bundle_version ?? GI_HISTORICAL_BENCHMARK_BUNDLE_VERSION,
      pilot_size: body?.pilot_size ?? GI_HISTORICAL_BENCHMARK_DEFAULT_PILOT_SIZE,
      random_seed: body?.random_seed ?? GI_HISTORICAL_BENCHMARK_DEFAULT_SEED,
    },
  )
}

export function startGoalIntensityBenchmarkJob(
  runId: number,
  body: {
    mode: 'pilot' | 'full'
    confirm: string
    bundle_version?: string
    pilot_size?: number
    random_seed?: number
    pilot_job_id?: number
    batch_size?: number
  },
): Promise<GiHistoricalBenchmarkJob> {
  return postJson(
    `/api/admin/cecchino-lab/historical/runs/${runId}/goal-intensity-benchmark/jobs`,
    {
      bundle_version: body.bundle_version ?? GI_HISTORICAL_BENCHMARK_BUNDLE_VERSION,
      pilot_size: body.pilot_size ?? GI_HISTORICAL_BENCHMARK_DEFAULT_PILOT_SIZE,
      random_seed: body.random_seed ?? GI_HISTORICAL_BENCHMARK_DEFAULT_SEED,
      ...body,
    },
  )
}

export function getGoalIntensityBenchmarkJob(
  jobId: number,
): Promise<GiHistoricalBenchmarkJob> {
  return requestJson(`/api/cecchino-lab/goal-intensity-benchmark/jobs/${jobId}`)
}

export function listGoalIntensityBenchmarkJobs(
  runId: number,
): Promise<{ jobs: GiHistoricalBenchmarkJob[] }> {
  return requestJson(`/api/cecchino-lab/historical/runs/${runId}/goal-intensity-benchmark/jobs`)
}

export function cancelGoalIntensityBenchmarkJob(
  jobId: number,
): Promise<GiHistoricalBenchmarkJob> {
  return postJson(`/api/admin/cecchino-lab/goal-intensity-benchmark/jobs/${jobId}/cancel`, {})
}

export function resumeGoalIntensityBenchmarkJob(
  jobId: number,
): Promise<GiHistoricalBenchmarkJob> {
  return postJson(`/api/admin/cecchino-lab/goal-intensity-benchmark/jobs/${jobId}/resume`, {})
}

export function downloadGoalIntensityBenchmarkExport(jobId: number): Promise<Blob> {
  const base = getApiBase()
  return fetch(`${base}/api/cecchino-lab/goal-intensity-benchmark/jobs/${jobId}/export`, {
    credentials: 'include',
  }).then(async (res) => {
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `Export failed (${res.status})`)
    }
    return res.blob()
  })
}

export function isGiHistoricalBenchmarkJobActive(status: string | null | undefined): boolean {
  return status === 'queued' || status === 'running' || status === 'cancel_requested'
}
